"""关注列表 DTO（Phase 5 Step 3）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai_alert import AiAlertOut
from app.utils.symbol import normalize


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=32)
    notes: str = Field(default="", max_length=256)

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize(v)


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    symbol: str
    notes: str
    added_at: datetime


# ── 盯盘驾驶舱 ──────────────────────────────────────────────


class BoardItem(BaseModel):
    symbol: str
    notes: str = ""
    name: str | None = None
    price: float | None = None
    pct_chg: float | None = None
    amount: float | None = None


class BoardOut(BaseModel):
    items: list[BoardItem]
    alerts: list[AiAlertOut]
    quote_ready: bool
