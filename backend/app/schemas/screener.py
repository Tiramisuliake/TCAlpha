"""选股器 DTO。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class LimitUpPremiumRequest(BaseModel):
    """涨停次日溢价统计请求（打板复盘）。"""

    symbol: str | None = None  # 单票；None = 全市场（已下载票）
    lookback: int = 250        # 回看交易日


class BoardGroupStat(BaseModel):
    boards: str       # 1板 / 2板 / 3板+
    count: int
    avg_open: float   # 次日平均开盘溢价
    avg_close: float  # 次日平均收盘溢价
    win_rate: float   # 次日红盘率
    promote_rate: float = 0.0  # 次日续板率（晋级 N+1 板的概率）


class LimitUpPremiumResult(BaseModel):
    ready: bool
    count: int
    avg_open_premium: float = 0.0
    avg_close_premium: float = 0.0
    avg_high_premium: float = 0.0
    next_day_win_rate: float = 0.0
    by_boards: list[BoardGroupStat] = []


class MatchPatternsRequest(BaseModel):
    """盯盘短线形态匹配请求。"""

    symbols: list[str] = Field(default_factory=list, max_length=300)


class PatternStatsRequest(BaseModel):
    """形态前瞻收益统计请求。"""

    pattern: str = "volume_breakout"
    symbol: str | None = None  # 单票；None = 全市场
    hold_days: int = Field(default=5, ge=1, le=60)
    lookback: int = Field(default=500, ge=20, le=2000)


class PatternStatsResult(BaseModel):
    ready: bool
    pattern: str
    hold_days: int
    count: int
    avg_return: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    median_return: float = 0.0
