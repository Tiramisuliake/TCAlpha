"""AI 助手路由（Phase 5：SSE 流式 chat）。"""
from __future__ import annotations

import json

from fastapi import APIRouter
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.schemas.ai import ChatRequest
from app.services import ai as ai_svc

router = APIRouter()


@router.post("/chat")
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
