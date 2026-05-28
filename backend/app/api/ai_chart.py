"""图表 AI 分析路由（Phase 5 Step 4：SSE 流式解读）。"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.auth_deps import require_permission
from app.services import ai_chart as ai_chart_svc

router = APIRouter()


@router.get(
    "/analyze",
    dependencies=[Depends(require_permission("ai.chat"))],
)
async def analyze(
    symbol: str = Query(..., min_length=2, max_length=20),
    period: Literal["1d"] = Query("1d"),
):
    """流式 K 线技术面解读。

    协议同 /api/ai/chat：data <chunk> 增量、data [DONE] 结束、data [ERROR]xxx 异常。
    """

    async def gen():
        try:
            async for chunk in ai_chart_svc.analyze_chart(symbol, period=period):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
            yield {"data": "[DONE]"}
        except Exception as exc:
            logger.exception("ai_chart analyze stream error: symbol={}", symbol)
            yield {"data": f"[ERROR]{type(exc).__name__}: {exc}"}

    return EventSourceResponse(gen())
