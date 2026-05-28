"""通知中心路由（Phase 5 Step 1）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_permission
from app.deps import DB, CurrentUserId
from app.schemas.notify import (
    CHANNELS,
    KNOWN_EVENT_TYPES,
    NotifyLogOut,
    NotifyRuleCreate,
    NotifyRuleOut,
    NotifyRuleUpdate,
    NotifyTestRequest,
)
from app.services import feishu as feishu_svc
from app.services import notify as notify_svc

router = APIRouter()


@router.get(
    "/event-types",
    dependencies=[Depends(require_permission("notify.rule.read"))],
)
async def list_event_types():
    """已注册事件类型 + 已支持渠道，供前端表单使用。"""
    return {"event_types": KNOWN_EVENT_TYPES, "channels": CHANNELS}


@router.get(
    "/rules",
    response_model=list[NotifyRuleOut],
    dependencies=[Depends(require_permission("notify.rule.read"))],
)
async def list_rules(user_id: int = CurrentUserId, db: AsyncSession = DB):
    return await notify_svc.list_rules(db, user_id)


@router.post(
    "/rules",
    response_model=NotifyRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("notify.rule.write"))],
)
async def create_rule(
    payload: NotifyRuleCreate,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await notify_svc.create_rule(db, user_id, payload)


@router.put(
    "/rules/{rule_id}",
    response_model=NotifyRuleOut,
    dependencies=[Depends(require_permission("notify.rule.write"))],
)
async def update_rule(
    rule_id: int,
    payload: NotifyRuleUpdate,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    obj = await notify_svc.update_rule(db, rule_id, user_id, payload)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return obj


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("notify.rule.write"))],
)
async def delete_rule(
    rule_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    ok = await notify_svc.delete_rule(db, rule_id, user_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")


@router.get(
    "/logs",
    response_model=list[NotifyLogOut],
    dependencies=[Depends(require_permission("notify.rule.read"))],
)
async def list_logs(
    limit: int = 100,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    rows = await notify_svc.list_logs(db, user_id, limit=min(limit, 500))
    return [NotifyLogOut.model_validate(r) for r in rows]


@router.post(
    "/test",
    dependencies=[Depends(require_permission("notify.rule.write"))],
)
async def test_push(
    payload: NotifyTestRequest,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """直接调飞书 API 试推一条文本（不走 event_bus，便于排查配置）。"""
    webhook = payload.feishu_webhook
    secret = payload.feishu_secret

    if payload.rule_id is not None:
        rule = await notify_svc.get_rule(db, payload.rule_id, user_id)
        if not rule:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
        webhook = webhook or rule.feishu_webhook
        secret = secret or rule.feishu_secret

    if not webhook:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "webhook 未提供")

    ok, err = await feishu_svc.send_text(webhook, secret, payload.content)
    return {"success": ok, "error": err}
