"""AI 盯盘告警查询。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_alert import AiAlert
from app.schemas.ai_alert import AiAlertOut


async def list_alerts(
    db: AsyncSession,
    user_id: int,
    *,
    level: str | None = None,
    symbol: str | None = None,
    only_unacked: bool = False,
    limit: int = 100,
) -> list[AiAlertOut]:
    stmt = select(AiAlert).where(AiAlert.user_id == user_id)
    if level:
        stmt = stmt.where(AiAlert.level == level)
    if symbol:
        stmt = stmt.where(AiAlert.symbol == symbol)
    if only_unacked:
        stmt = stmt.where(AiAlert.acked.is_(False))
    stmt = stmt.order_by(AiAlert.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [AiAlertOut.model_validate(r) for r in rows]


async def ack_alert(db: AsyncSession, user_id: int, alert_id: int) -> bool:
    stmt = select(AiAlert).where(AiAlert.id == alert_id, AiAlert.user_id == user_id)
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        return False
    obj.acked = True
    await db.commit()
    return True
