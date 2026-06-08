"""选股器 DTO。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ScreenRequest(BaseModel):
    market_cap_min: float | None = None  # 亿元
    market_cap_max: float | None = None  # 亿元
    pe_min: float | None = None
    pe_max: float | None = None
    amount_min: float | None = None  # 亿元（成交额下限）
    turnover_min: float | None = None  # %（换手率下限）
    pct_chg_min: float | None = None  # %
    pct_chg_max: float | None = None
    exclude_st: bool = False
    sort_by: str = "amount"
    limit: int = 50
    # 多因子打分（factor_mode=True 时按综合得分排序，覆盖 sort_by）
    factor_mode: bool = False
    w_momentum: float = 1.0  # 动量：涨幅越高越优
    w_value: float = 1.0     # 估值：PE 越低越优（仅 PE>0 计分）
    w_turnover: float = 1.0  # 活跃：换手率越高越优


class ScreenResult(BaseModel):
    ready: bool
    count: int
    candidates: list[dict[str, Any]]
