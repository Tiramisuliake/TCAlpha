"""投研报告路由（AI 周报）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from app.core.auth_deps import require_permission
from app.deps import CurrentUserId
from app.services import weekly_report as weekly_svc

router = APIRouter()


@router.get(
    "/weekly",
    response_class=HTMLResponse,
    dependencies=[Depends(require_permission("data.read"))],
)
async def weekly_report(
    user_id: int = CurrentUserId,
    ai: bool = Query(default=True, description="是否生成 AI 综述段落（失败自动降级）"),
):
    """生成 AI 投研周报（账户净值周复盘 + 市场情绪周走势 + AI 综述），自包含 HTML 下载。"""
    data = await asyncio.to_thread(weekly_svc.collect_weekly_sync, user_id)
    ai_text = await weekly_svc.ai_weekly_summary(data) if ai else ""
    html = weekly_svc.build_weekly_html(data, ai_text)
    return HTMLResponse(
        html,
        headers={"Content-Disposition": "attachment; filename=tcalpha_weekly.html"},
    )
