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


class ShortTermRequest(BaseModel):
    """短线技术选股请求（基于 ArcticDB 历史日 K 的量价形态）。"""

    pattern: str = "volume_breakout"  # volume_breakout / ma_long / pullback / limit_up
    breakout_window: int = 20         # 突破窗口（前 N 日新高）
    vol_window: int = 5               # 量比基准窗口
    vol_ratio_min: float = 1.5        # 放量倍数下限（volume_breakout 用）
    min_boards: int = 1               # 连板下限（limit_up 用，1=今日涨停）
    price_min: float | None = None    # 股价下限（元）
    price_max: float | None = None    # 股价上限（元）
    exclude_st: bool = True
    limit: int = 50
