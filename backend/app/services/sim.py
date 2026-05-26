"""模拟交易业务逻辑（Phase 4）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import get_sync_redis, running_key, stop_key
from app.db.models.order import SimOrder
from app.db.models.strategy import StrategyConfig
from app.schemas.sim import PositionOut, SimOrderOut


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
    db: AsyncSession, user_id: int, strategy_id: int | None = None, limit: int = 50
) -> list[SimOrderOut]:
    stmt = select(SimOrder).where(SimOrder.user_id == user_id)
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
