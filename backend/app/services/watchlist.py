"""Watchlist 业务逻辑。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistCreate, WatchlistOut


async def list_items(db: AsyncSession, user_id: int) -> list[WatchlistOut]:
    stmt = (
        select(Watchlist)
        .where(Watchlist.user_id == user_id)
        .order_by(Watchlist.added_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [WatchlistOut.model_validate(r) for r in rows]


async def add_item(
    db: AsyncSession, user_id: int, payload: WatchlistCreate
) -> WatchlistOut | None:
    obj = Watchlist(user_id=user_id, symbol=payload.symbol, notes=payload.notes)
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(obj)
    return WatchlistOut.model_validate(obj)


async def remove_item(db: AsyncSession, user_id: int, item_id: int) -> bool:
    stmt = select(Watchlist).where(
        Watchlist.id == item_id, Watchlist.user_id == user_id
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True
