"""通知中心业务逻辑（Phase 5 Step 1）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notify import NotifyLog, NotifyRule
from app.schemas.notify import NotifyRuleCreate, NotifyRuleOut, NotifyRuleUpdate


async def list_rules(db: AsyncSession, user_id: int) -> list[NotifyRuleOut]:
    stmt = (
        select(NotifyRule)
        .where(NotifyRule.user_id == user_id)
        .order_by(NotifyRule.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [NotifyRuleOut.model_validate(r) for r in rows]


async def get_rule(db: AsyncSession, rule_id: int, user_id: int) -> NotifyRule | None:
    stmt = select(NotifyRule).where(
        NotifyRule.id == rule_id, NotifyRule.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_rule(
    db: AsyncSession, user_id: int, payload: NotifyRuleCreate
) -> NotifyRuleOut:
    obj = NotifyRule(user_id=user_id, **payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return NotifyRuleOut.model_validate(obj)


async def update_rule(
    db: AsyncSession, rule_id: int, user_id: int, payload: NotifyRuleUpdate
) -> NotifyRuleOut | None:
    obj = await get_rule(db, rule_id, user_id)
    if not obj:
        return None
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return NotifyRuleOut.model_validate(obj)


async def delete_rule(db: AsyncSession, rule_id: int, user_id: int) -> bool:
    obj = await get_rule(db, rule_id, user_id)
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def list_logs(
    db: AsyncSession, user_id: int, limit: int = 100
) -> list[NotifyLog]:
    stmt = (
        select(NotifyLog)
        .where(NotifyLog.user_id == user_id)
        .order_by(NotifyLog.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())
