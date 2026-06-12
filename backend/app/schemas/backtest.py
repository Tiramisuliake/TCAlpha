"""回测 DTO。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    benchmark: str = "000300"  # 对比基准指数代码
    period: str = "1d"  # K 线周期：1d / 60m / 30m / 15m / 5m / 1m


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


class SweepSubmit(BaseModel):
    name: str
    class_name: str
    symbol: str
    param_grid: dict[str, list[float]] = {}
    target: str = "sharpe"
    start_date: date
    end_date: date
    init_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.01
    period: str = "1d"  # K 线周期
    # Walk-Forward 验证集占比（0~0.6）：按时间切训练/验证段，None = 不切分
    oos_split: float | None = Field(default=None, ge=0.05, le=0.6)


class SweepStatusOut(BaseModel):
    job_id: int
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
