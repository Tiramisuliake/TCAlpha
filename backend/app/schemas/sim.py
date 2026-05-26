"""模拟交易 DTO。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SimOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int | None
    symbol: str
    direction: str
    offset: str
    price: float
    volume: int
    filled_volume: int
    status: str
    created_at: datetime
    updated_at: datetime


class PositionOut(BaseModel):
    symbol: str
    net_position: int


class StrategySignal(BaseModel):
    strategy_id: int
    symbol: str
    bar_dt: str
    direction: int
    strength: int
    tip: str
    pos: int
    ts: str
