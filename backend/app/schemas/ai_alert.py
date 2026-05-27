"""AI 盯盘 DTO（Phase 5 Step 3）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AlertLevel = Literal["info", "warn", "danger"]


class WatchResult(BaseModel):
    """AI 严格输出：用于盯盘结论的 JSON schema。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    level: AlertLevel = Field(description="info=提示, warn=预警, danger=紧急")
    signal: str = Field(min_length=1, max_length=256, description="一句话信号摘要")
    reason: str = Field(min_length=1, max_length=2000, description="完整理由")


class AiAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    symbol: str
    level: str
    signal: str
    reason: str
    snapshot: dict[str, Any]
    acked: bool
    created_at: datetime
