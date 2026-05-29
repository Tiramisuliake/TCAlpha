"""模拟交易 DTO。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PositionSummary(BaseModel):
    """多 symbol 持仓汇总单行。"""

    symbol: str
    net_position: int


class PlaceOrderRequest(BaseModel):
    """手工下单请求（市价单立即成交）。"""

    symbol: str = Field(..., description="股票代码，sh600000 或 600000")
    direction: Literal["long", "short"] = Field(..., description="方向：long 多 / short 空")
    offset: Literal["open", "close"] = Field(..., description="开平：open 开仓 / close 平仓")
    volume: int = Field(..., gt=0, description="数量，会向下取整到 100 股")


class StrategySignal(BaseModel):
    strategy_id: int
    symbol: str
    bar_dt: str
    direction: int
    strength: int
    tip: str
    pos: int
    ts: str
