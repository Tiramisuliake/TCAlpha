"""AI 盯盘告警 API + 手动触发（Phase 5 Step 3）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import CurrentUser, effective_scope, require_permission
from app.deps import DB, CurrentUserId
from app.schemas.ai_alert import AiAlertOut
from app.services import ai_alerts as alerts_svc

router = APIRouter()


@router.get(
    "",
    response_model=list[AiAlertOut],
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def list_alerts(
    user: CurrentUser,
    level: str | None = None,
    symbol: str | None = None,
    only_unacked: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = DB,
):
    return await alerts_svc.list_alerts(
        db, user.id,
        level=level, symbol=symbol, only_unacked=only_unacked, limit=limit,
        scope=effective_scope(user),
    )


@router.post(
    "/{alert_id}/ack",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def ack_alert(
    alert_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    ok = await alerts_svc.ack_alert(db, user_id, alert_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")


@router.post(
    "/watch/{symbol}",
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def trigger_watch(
    symbol: str,
    user_id: int = CurrentUserId,
):
    """手动触发对单个标的的 AI 盯盘（不等 beat 周期）。

    走 Celery task 异步执行；返回 task_id，前端可轮询 ai-alerts 列表。
    """
    from app.tasks.ai_tasks import ai_watch_one

    result = ai_watch_one.delay(user_id, symbol)
    return {"task_id": result.id, "status": "queued"}
