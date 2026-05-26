"""AI 助手 DTO（Phase 5）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """OpenAI 兼容的单条消息。"""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """前端发送的对话请求体。

    - `messages` 是多轮历史（含最新一条 user 消息），由前端维护。
    - `system` 可选，用于覆盖默认系统 prompt。
    - `temperature` 范围 [0, 2]，默认 0.7。
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    system: str | None = Field(default=None, max_length=2000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
