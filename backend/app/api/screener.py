"""选股器路由（基于全市场快照按条件筛选）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth_deps import require_permission
from app.deps import CurrentUserId
from app.schemas.screener import ScreenRequest, ScreenResult
from app.services import screener as screener_svc

router = APIRouter()


@router.post(
    "/run",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_screen(
    payload: ScreenRequest,
    _: int = CurrentUserId,
):
    """按市值/PE/成交额/换手/涨跌幅等条件筛选候选股（读 Redis 全市场快照缓存）。"""
    return await screener_svc.screen(payload.model_dump())
