"""策略业务逻辑（Phase 3）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.backtest_engine import list_strategy_classes
from app.db.models.strategy import StrategyConfig
from app.schemas.strategy import StrategyCreate, StrategyOut


async def list_strategies(
    db: AsyncSession, user_id: int, scope: str = "self"
) -> list[StrategyOut]:
    stmt = select(StrategyConfig).order_by(StrategyConfig.created_at.desc())
    if scope != "all":
        stmt = stmt.where(StrategyConfig.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [StrategyOut.model_validate(r) for r in rows]


async def create_strategy(
    db: AsyncSession, user_id: int, payload: StrategyCreate
) -> StrategyOut:
    obj = StrategyConfig(
        user_id=user_id,
        name=payload.name,
        class_name=payload.class_name,
        symbol=payload.symbol,
        params=payload.params,
        state={},
        status="stopped",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return StrategyOut.model_validate(obj)


async def update_strategy(
    db: AsyncSession, strategy_id: int, user_id: int, payload: StrategyCreate
) -> StrategyOut | None:
    stmt = select(StrategyConfig).where(
        StrategyConfig.id == strategy_id, StrategyConfig.user_id == user_id
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        return None
    obj.name = payload.name
    obj.class_name = payload.class_name
    obj.symbol = payload.symbol
    obj.params = payload.params
    await db.commit()
    await db.refresh(obj)
    return StrategyOut.model_validate(obj)


async def delete_strategy(db: AsyncSession, strategy_id: int, user_id: int) -> bool:
    stmt = select(StrategyConfig).where(
        StrategyConfig.id == strategy_id, StrategyConfig.user_id == user_id
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def can_subscribe_signals(
    db: AsyncSession, strategy_id: int, user_id: int, *, is_super: bool = False
) -> bool:
    """校验用户是否可订阅某个策略的信号推送。"""
    if is_super:
        return (
            await db.execute(select(StrategyConfig.id).where(StrategyConfig.id == strategy_id))
        ).scalar_one_or_none() is not None
    stmt = select(StrategyConfig.id).where(
        StrategyConfig.id == strategy_id,
        StrategyConfig.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


def get_strategy_classes() -> list[dict]:
    return list_strategy_classes()
