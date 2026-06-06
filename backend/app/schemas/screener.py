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


class ScreenResult(BaseModel):
    ready: bool
    count: int
    candidates: list[dict[str, Any]]
