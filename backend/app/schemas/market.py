"""行情 DTO（Phase 1）。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    code: str
    exchange: str
    name: str
    industry: str | None = None
    list_date: date | None = None
    is_active: bool


class SymbolListResponse(BaseModel):
    items: list[SymbolOut]
    total: int


class KlineBar(BaseModel):
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


class KlineResponse(BaseModel):
    symbol: str
    period: str
    bars: list[KlineBar]
    total: int


class DownloadTriggerResponse(BaseModel):
    symbol: str
    task_id: str
    message: str = Field(default="download task submitted")


class RefreshTriggerResponse(BaseModel):
    task_id: str
    message: str = Field(default="refresh task submitted")
