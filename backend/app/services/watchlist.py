"""Watchlist 业务逻辑。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistCreate, WatchlistOut


async def list_items(db: AsyncSession, user_id: int) -> list[WatchlistOut]:
    """自选列表。刻意不接 data_scope：自选股是个人配置而非业务产出，
    跨用户可见无监控价值（Phase 8 设计决定，notify 规则同理且含 webhook 密钥）。"""
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


async def get_board(db: AsyncSession, user_id: int):
    """盯盘驾驶舱聚合：自选股 + 实时报价（快照）+ 最近 AI 告警。"""
    from app.schemas.watchlist import BoardItem, BoardOut
    from app.services.ai_alerts import list_alerts
    from app.services.screener import get_snapshot_quotes

    items = await list_items(db, user_id)
    quotes = await get_snapshot_quotes([i.symbol for i in items])
    alerts = await list_alerts(db, user_id, limit=20)

    board_items: list[BoardItem] = []
    for i in items:
        q = quotes.get(i.symbol, {})
        board_items.append(
            BoardItem(
                symbol=i.symbol,
                notes=i.notes,
                name=q.get("name"),
                price=q.get("price"),
                pct_chg=q.get("pct_chg"),
                amount=q.get("amount"),
            )
        )
    return BoardOut(items=board_items, alerts=alerts, quote_ready=bool(quotes))
