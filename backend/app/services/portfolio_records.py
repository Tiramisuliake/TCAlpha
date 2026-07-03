"""组合回测结果存档 CRUD（按用户隔离）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.portfolio_record import PortfolioBacktestRecord


async def save_record(
    db: AsyncSession, user_id: int, name: str, kind: str, config: dict, metrics: dict
) -> PortfolioBacktestRecord:
    obj = PortfolioBacktestRecord(
        user_id=user_id, name=name, kind=kind, config=config, metrics=metrics
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def list_records(
    db: AsyncSession, user_id: int, limit: int = 50
) -> list[PortfolioBacktestRecord]:
    stmt = (
        select(PortfolioBacktestRecord)
        .where(PortfolioBacktestRecord.user_id == user_id)
        .order_by(PortfolioBacktestRecord.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_record(db: AsyncSession, user_id: int, record_id: int) -> bool:
    stmt = select(PortfolioBacktestRecord).where(
        PortfolioBacktestRecord.id == record_id,
        PortfolioBacktestRecord.user_id == user_id,
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        return False
    await db.delete(obj)
    await db.commit()
    return True
