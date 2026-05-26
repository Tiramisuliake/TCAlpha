"""AI 服务：OpenAI 兼容 API + 流式输出（Phase 5）。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from loguru import logger
from openai import APIError, AsyncOpenAI

from app.config import settings
from app.schemas.ai import ChatMessage

_DEFAULT_SYSTEM = (
    "你是 TCAlpha 量化交易助手。回答需简洁、客观、专业，使用中文。"
    "涉及操作建议时明确标注'仅供参考，不构成投资建议'。"
)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """全局单例 OpenAI 兼容客户端。"""
    global _client
    if _client is None:
        if not settings.ai_api_key:
            raise RuntimeError(
                "AI_API_KEY 未配置，请在 .env 中设置 AI_API_KEY"
            )
        _client = AsyncOpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_api_base,
        )
    return _client


async def stream_chat(
    messages: list[ChatMessage],
    system: str | None = None,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """流式生成 chat 回复，逐 chunk yield 文本片段。"""
    payload = [{"role": "system", "content": system or _DEFAULT_SYSTEM}]
    payload.extend(m.model_dump() for m in messages)

    try:
        resp = await get_client().chat.completions.create(
            model=settings.ai_model,
            messages=payload,
            stream=True,
            temperature=temperature,
        )
        async for chunk in resp:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except APIError as exc:
        logger.warning("AI APIError: {}", exc)
        raise
    except Exception:
        logger.exception("AI stream_chat unexpected failure")
        raise
