"""模拟交易业务逻辑（Phase 4 + 手工下单扩展）。"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.pubsub import get_sync_redis, publish_order, running_key, stop_key
from app.db.models.account import SimAccount
from app.db.models.order import SimOrder
from app.db.models.strategy import StrategyConfig
from app.schemas.sim import (
    AccountOut,
    AccountPosition,
    PositionOut,
    PositionSummary,
    SimOrderOut,
)
from app.utils.symbol import normalize

# 费率与 SimGateway 保持一致
_COMMISSION_RATE = 0.0003
_STAMP_DUTY = 0.001  # 卖出印花税


async def start_strategy(db: AsyncSession, strategy_id: int, user_id: int) -> dict:
    """启动策略 Celery 任务，更新 DB 状态，返回 task_id。"""
    stmt = select(StrategyConfig).where(
        StrategyConfig.id == strategy_id, StrategyConfig.user_id == user_id
    )
    cfg = (await db.execute(stmt)).scalar_one_or_none()
    if not cfg:
        return {"error": "strategy not found"}

    r = get_sync_redis()
    if r.exists(running_key(strategy_id)):
        return {"error": "strategy already running", "running": True}

    from app.tasks.strategy_tasks import run_strategy

    result = run_strategy.delay(strategy_id)
    cfg.status = "running"
    await db.commit()

    return {"task_id": result.id, "strategy_id": strategy_id, "status": "running"}


async def stop_strategy(db: AsyncSession, strategy_id: int, user_id: int) -> dict:
    """设置 Redis stop 标志，让长跑任务自行退出。"""
    stmt = select(StrategyConfig).where(
        StrategyConfig.id == strategy_id, StrategyConfig.user_id == user_id
    )
    cfg = (await db.execute(stmt)).scalar_one_or_none()
    if not cfg:
        return {"error": "strategy not found"}

    r = get_sync_redis()
    r.set(stop_key(strategy_id), "1", ex=300)

    cfg.status = "stopped"
    await db.commit()
    return {"strategy_id": strategy_id, "status": "stopped"}


async def list_orders(
    db: AsyncSession,
    user_id: int,
    strategy_id: int | None = None,
    limit: int = 50,
    scope: str = "self",
) -> list[SimOrderOut]:
    stmt = select(SimOrder)
    if scope != "all":
        stmt = stmt.where(SimOrder.user_id == user_id)
    if strategy_id is not None:
        stmt = stmt.where(SimOrder.strategy_id == strategy_id)
    stmt = stmt.order_by(SimOrder.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [SimOrderOut.model_validate(r) for r in rows]


async def get_position(db: AsyncSession, user_id: int, symbol: str) -> PositionOut:
    stmt = select(SimOrder).where(
        SimOrder.user_id == user_id,
        SimOrder.symbol == symbol,
        SimOrder.status == "filled",
    )
    rows = (await db.execute(stmt)).scalars().all()
    pos = 0
    for o in rows:
        sign = 1 if o.direction == "long" else -1
        sign *= 1 if o.offset == "open" else -1
        pos += sign * o.filled_volume
    return PositionOut(symbol=symbol, net_position=pos)


def get_strategy_running_status(strategy_id: int) -> bool:
    r = get_sync_redis()
    return bool(r.exists(running_key(strategy_id)))


# ──────────────────────────────────────────────
# 手工下单（市价单立即成交） / 撤单 / 多 symbol 持仓
# ──────────────────────────────────────────────

_VALID_DIRECTIONS = {"long", "short"}
_VALID_OFFSETS = {"open", "close"}
_LOT = 100  # A 股最小交易单位


def _publish_order_event(order: SimOrder) -> None:
    """同步发 Redis pub/sub（publish_order 是同步 redis client）。"""
    try:
        publish_order(
            order.user_id,
            {
                "id": order.id,
                "symbol": order.symbol,
                "direction": order.direction,
                "offset": order.offset,
                "price": order.price,
                "volume": order.volume,
                "filled_volume": order.filled_volume,
                "status": order.status,
                "strategy_id": order.strategy_id,
            },
        )
    except Exception as exc:
        logger.warning("publish_order failed for order {}: {}", order.id, exc)


async def place_market_order(
    db: AsyncSession,
    user_id: int,
    symbol: str,
    direction: str,
    offset: str,
    volume: int,
) -> SimOrderOut:
    """手工市价单立即成交：拿当前实时报价 → 写 filled 订单。

    校验：direction/offset 枚举；volume 向下取整到 100 股；
    成交价由 ``fetch_single_quote`` 提供，若拿不到则用 0（拒单）。
    """
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction}")
    if offset not in _VALID_OFFSETS:
        raise ValueError(f"invalid offset: {offset}")
    sym = normalize(symbol)
    vol = max((int(volume) // _LOT) * _LOT, _LOT)

    # fetch_single_quote 同步 + 走 requests，必须丢到线程池避免阻塞事件循环
    from app.services.quote import fetch_single_quote

    quote = await asyncio.to_thread(fetch_single_quote, sym)
    if not quote or quote.get("price") is None:
        # 拿不到报价 → 拒单（status=rejected, price=0）
        order = SimOrder(
            user_id=user_id,
            symbol=sym,
            direction=direction,
            offset=offset,
            price=0.0,
            volume=vol,
            filled_volume=0,
            status="rejected",
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        _publish_order_event(order)
        logger.warning("place_market_order rejected: no quote for {}", sym)
        return SimOrderOut.model_validate(order)

    price = float(quote["price"])

    # 资金账户结算：开仓验余额并扣款；平仓入账（含印花税）
    acct = await _get_or_create_account(db, user_id)
    if offset == "open":
        cost = price * vol * (1 + _COMMISSION_RATE)
        if acct.balance < cost:
            order = SimOrder(
                user_id=user_id,
                symbol=sym,
                direction=direction,
                offset=offset,
                price=price,
                volume=vol,
                filled_volume=0,
                status="rejected",
            )
            db.add(order)
            await db.commit()
            await db.refresh(order)
            _publish_order_event(order)
            logger.warning(
                "place_market_order rejected (insufficient balance): user={} need={:.2f} have={:.2f}",
                user_id, cost, acct.balance,
            )
            return SimOrderOut.model_validate(order)
        acct.balance -= cost
    else:
        acct.balance += price * vol * (1 - _COMMISSION_RATE - _STAMP_DUTY)

    order = SimOrder(
        user_id=user_id,
        symbol=sym,
        direction=direction,
        offset=offset,
        price=price,
        volume=vol,
        filled_volume=vol,
        status="filled",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    _publish_order_event(order)
    logger.info(
        "place_market_order: user={} {} {} {} vol={} @ {}",
        user_id, sym, direction, offset, vol, price,
    )
    return SimOrderOut.model_validate(order)


async def cancel_order(
    db: AsyncSession, user_id: int, order_id: int
) -> SimOrderOut | None:
    """撤单：仅 submitted 可撤；校验所有权；失败返回 None。"""
    stmt = select(SimOrder).where(
        SimOrder.id == order_id, SimOrder.user_id == user_id
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        return None
    if order.status != "submitted":
        # 已成交 / 已撤 → 幂等返回当前状态，不报错
        return SimOrderOut.model_validate(order)

    order.status = "cancelled"
    order.updated_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(order)
    _publish_order_event(order)
    logger.info("cancel_order: user={} order_id={}", user_id, order_id)
    return SimOrderOut.model_validate(order)


# ──────────────────────────────────────────────
# 资金账户（v0.8.6）
# ──────────────────────────────────────────────


async def _get_or_create_account(db: AsyncSession, user_id: int) -> SimAccount:
    """懒创建资金账户（初始资金走 settings.sim_init_capital）。"""
    stmt = select(SimAccount).where(SimAccount.user_id == user_id)
    acct = (await db.execute(stmt)).scalar_one_or_none()
    if acct is None:
        acct = SimAccount(
            user_id=user_id,
            balance=settings.sim_init_capital,
            init_capital=settings.sim_init_capital,
        )
        db.add(acct)
        await db.flush()
    return acct


async def get_account(db: AsyncSession, user_id: int) -> AccountOut:
    """账户快照：现金 + 持仓成本（按时序重放 filled 订单，加权摊薄均价）。

    成本口径：total_asset = 现金 + 持仓成本，不做实时市值 mark-to-market
    （盘中报价另有 quote 通道，账户页先给确定性的成本视图）。
    """
    acct = await _get_or_create_account(db, user_id)
    await db.commit()  # 持久化懒创建

    stmt = (
        select(SimOrder)
        .where(SimOrder.user_id == user_id, SimOrder.status == "filled")
        .order_by(SimOrder.created_at, SimOrder.id)
    )
    rows = (await db.execute(stmt)).scalars().all()

    pos_map: dict[str, dict] = {}  # symbol → {pos, avg}
    for o in rows:
        eff = o.filled_volume * (1 if (o.direction == "long") == (o.offset == "open") else -1)
        st = pos_map.setdefault(o.symbol, {"pos": 0, "avg": 0.0})
        if eff > 0:
            total = st["avg"] * st["pos"] + o.price * eff
            st["pos"] += eff
            st["avg"] = total / st["pos"] if st["pos"] > 0 else 0.0
        else:
            st["pos"] = max(st["pos"] + eff, 0)
            if st["pos"] == 0:
                st["avg"] = 0.0

    positions = [
        AccountPosition(
            symbol=sym,
            volume=st["pos"],
            avg_price=round(st["avg"], 4),
            cost=round(st["avg"] * st["pos"], 2),
        )
        for sym, st in pos_map.items()
        if st["pos"] > 0
    ]
    position_cost = round(sum(p.cost for p in positions), 2)
    return AccountOut(
        balance=round(acct.balance, 2),
        init_capital=acct.init_capital,
        position_cost=position_cost,
        total_asset=round(acct.balance + position_cost, 2),
        positions=positions,
    )


async def reset_account(db: AsyncSession, user_id: int) -> AccountOut:
    """重置账户：现金回到初始资金（订单流水保留，仅作审计）。"""
    acct = await _get_or_create_account(db, user_id)
    acct.balance = acct.init_capital
    await db.commit()
    logger.info("reset_account: user={} balance→{}", user_id, acct.init_capital)
    return await get_account(db, user_id)


async def list_positions(
    db: AsyncSession, user_id: int
) -> list[PositionSummary]:
    """聚合所有 filled 订单，按 symbol 算净持仓；过滤掉 net=0 的。"""
    stmt = select(SimOrder).where(
        SimOrder.user_id == user_id,
        SimOrder.status == "filled",
    )
    rows = (await db.execute(stmt)).scalars().all()

    by_symbol: dict[str, int] = {}
    for o in rows:
        sign = 1 if o.direction == "long" else -1
        sign *= 1 if o.offset == "open" else -1
        by_symbol[o.symbol] = by_symbol.get(o.symbol, 0) + sign * o.filled_volume

    return [
        PositionSummary(symbol=sym, net_position=pos)
        for sym, pos in by_symbol.items()
        if pos != 0
    ]
