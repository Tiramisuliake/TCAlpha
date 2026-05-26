"""回测 DTO。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BacktestSubmit(BaseModel):
    name: str
    class_name: str
    symbol: str
    params: dict[str, Any] = {}
    start_date: date
    end_date: date
    init_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.01


class BacktestStatusOut(BaseModel):
    job_id: int
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class BacktestTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    symbol: str
    direction: str
    offset: str
    price: float
    volume: int
    dt: datetime
    pnl: float | None = None
