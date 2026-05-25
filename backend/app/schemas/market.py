"""行情 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BarOut(BaseModel):
    symbol: str
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


class KlineQuery(BaseModel):
    symbol: str
    period: str = "1d"
    limit: int = 200
