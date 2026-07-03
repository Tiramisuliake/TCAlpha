"""组合回测结果存档 CRUD（按用户隔离）。"""
from __future__ import annotations

from sqlalchemy import delete, select
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
    result = await db.execute(
        delete(PortfolioBacktestRecord).where(
            PortfolioBacktestRecord.id == record_id,
            PortfolioBacktestRecord.user_id == user_id,
        )
    )
    await db.commit()
    return (result.rowcount or 0) > 0
