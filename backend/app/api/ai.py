"""AI 助手路由（Phase 5：SSE 流式 chat）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.auth_deps import require_permission
from app.deps import DB, CurrentUserId
from app.schemas.ai import ChatRequest
from app.services import ai as ai_svc
from app.services import ai_backtest as ai_backtest_svc

router = APIRouter()


@router.post(
    "/chat",
    dependencies=[Depends(require_permission("ai.chat"))],
)
async def chat(payload: ChatRequest):
    """流式 chat：SSE 把 LLM 输出分块推送到前端。

    协议：
      - `data: <chunk>` 每个增量片段
      - `data: [DONE]` 正常结束
      - `data: [ERROR]<msg>` 异常结束（如未配置 API key）
    """

    async def gen():
        try:
            async for chunk in ai_svc.stream_chat(
                payload.messages,
                system=payload.system,
                temperature=payload.temperature,
            ):
                # JSON 序列化避免换行 / 反斜杠破坏 SSE 帧
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
            yield {"data": "[DONE]"}
        except Exception as exc:
            logger.exception("AI chat stream error")
            yield {"data": f"[ERROR]{type(exc).__name__}: {exc}"}

    return EventSourceResponse(gen())


@router.get(
    "/backtest/{job_id}/analyze",
    dependencies=[Depends(require_permission("ai.chat"))],
)
async def analyze_backtest(
    job_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """流式回测绩效归因：SSE 推送 LLM 解读。协议同 /chat。"""

    async def gen():
        try:
            async for chunk in ai_backtest_svc.analyze_backtest(db, job_id, user_id):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
            yield {"data": "[DONE]"}
        except Exception as exc:
            logger.exception("AI backtest analyze error: job_id={}", job_id)
            yield {"data": f"[ERROR]{type(exc).__name__}: {exc}"}

    return EventSourceResponse(gen())
