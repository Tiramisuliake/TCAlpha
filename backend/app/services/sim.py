"""模拟交易业务逻辑（Phase 4 + 手工下单扩展）。"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import get_sync_redis, publish_order, running_key, stop_key
from app.db.models.order import SimOrder
from app.db.models.strategy import StrategyConfig
from app.schemas.sim import PositionOut, PositionSummary, SimOrderOut
from app.utils.symbol import normalize


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
