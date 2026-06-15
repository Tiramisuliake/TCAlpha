"""选股器路由（基于全市场快照按条件筛选）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.core.auth_deps import require_permission
from app.deps import CurrentUserId
from app.schemas.screener import ScreenRequest, ScreenResult, ShortTermRequest
from app.services import screener as screener_svc
from app.services import short_term as short_term_svc

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


@router.post(
    "/short-term",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_short_term(
    payload: ShortTermRequest,
    _: int = CurrentUserId,
):
    """短线技术选股：按量价形态（放量突破 / 均线多头 / 回踩企稳）扫描 ArcticDB 历史 K。

    扫描读 ArcticDB（同步 IO），丢线程池避免阻塞事件循环。
    """
    return await asyncio.to_thread(short_term_svc.scan_short_term, payload.model_dump())
