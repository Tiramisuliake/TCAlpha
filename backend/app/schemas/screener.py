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


class ResonanceRequest(BaseModel):
    """多形态共振筛选请求。"""

    min_patterns: int = Field(default=2, ge=2, le=4)  # 最少同时命中形态数
    vol_ratio_min: float = 1.5
    price_min: float | None = None
    price_max: float | None = None
    exclude_st: bool = True
    limit: int = 50


class PatternMarker(BaseModel):
    """K 线图形态命中标记：某日命中的形态中文名列表。"""

    dt: str
    patterns: list[str]


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


class PatternStatsAllRequest(BaseModel):
    """全形态前瞻收益对比请求。"""

    hold_days: int = Field(default=5, ge=1, le=60)
    lookback: int = Field(default=500, ge=20, le=2000)


class FactorWeights(BaseModel):
    """多因子综合打分权重（缺省等权，0 表示该因子不参与）。"""

    mom_20: float = Field(default=1.0, ge=0, le=10)       # 20日动量
    mom_60: float = Field(default=1.0, ge=0, le=10)       # 60日动量
    volatility: float = Field(default=1.0, ge=0, le=10)   # 低波动溢价
    trend_slope: float = Field(default=1.0, ge=0, le=10)  # 趋势斜率
    vol_surge: float = Field(default=1.0, ge=0, le=10)    # 量能放大
    # 反转 / 超卖风格（缺省 0，不参与；用户按需开启与动量对冲）
    rev_5: float = Field(default=0.0, ge=0, le=10)        # 5日反转
    rsi_14: float = Field(default=0.0, ge=0, le=10)       # RSI 超卖
    boll_pctb: float = Field(default=0.0, ge=0, le=10)    # 布林%B 位置
    # 量价 / 资金行为（缺省 0，按需开启）
    corr_pv: float = Field(default=0.0, ge=0, le=10)      # 量价相关性
    amihud: float = Field(default=0.0, ge=0, le=10)       # Amihud 非流动性
    obv_slope: float = Field(default=0.0, ge=0, le=10)    # OBV 斜率


class FactorScreenRequest(BaseModel):
    """时序多因子选股请求（基于 ArcticDB 历史日 K 计算的连续因子）。"""

    weights: FactorWeights = Field(default_factory=FactorWeights)
    price_min: float | None = None
    price_max: float | None = None
    exclude_st: bool = True
    limit: int = Field(default=50, ge=1, le=200)
    max_scan: int = Field(default=800, ge=1, le=5000)


class FactorICRequest(BaseModel):
    """单因子有效性检验请求（IC + 分层回测）。"""

    factor: str = "mom_20"
    hold_days: int = Field(default=10, ge=1, le=60)        # 前瞻持有天数
    lookback: int = Field(default=240, ge=40, le=1000)     # 采样回看窗口（交易日）
    sample_points: int = Field(default=8, ge=3, le=30)     # 采样时点数
    max_scan: int = Field(default=300, ge=1, le=2000)      # 扫描标的上限


class QuantileReturn(BaseModel):
    q: int             # 分档 1..5（1 = 因子值最低档）
    avg_return: float  # 该档未来 hold_days 平均收益


class FactorICAllRequest(BaseModel):
    """全因子 IC 横评请求。"""

    hold_days: int = Field(default=10, ge=1, le=60)
    lookback: int = Field(default=240, ge=40, le=1000)
    sample_points: int = Field(default=8, ge=3, le=30)
    max_scan: int = Field(default=300, ge=1, le=2000)


class FactorICSummary(BaseModel):
    factor: str
    name: str                  # 因子中文名
    sample_count: int
    mean_ic: float = 0.0
    ic_ir: float = 0.0
    ic_win_rate: float = 0.0
    long_short: float = 0.0    # 多空收益（按因子方向对齐）


class FactorPortfolioRequest(BaseModel):
    """多因子组合回测请求。"""

    weights: FactorWeights = Field(default_factory=FactorWeights)
    top_n: int = Field(default=10, ge=1, le=100)          # 每期持仓数
    rebalance_days: int = Field(default=20, ge=1, le=120)  # 调仓周期（交易日）
    lookback: int = Field(default=480, ge=40, le=2000)    # 回测回看窗口
    max_scan: int = Field(default=300, ge=1, le=2000)


class PortfolioPoint(BaseModel):
    dt: str
    value: float


class FactorPortfolioResult(BaseModel):
    ready: bool
    rebalance_count: int = 0
    top_n: int = 0
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0          # 调仓周期胜率
    excess_return: float = 0.0     # 对全市场等权基准的超额
    equity_curve: list[PortfolioPoint] = []
    benchmark_curve: list[PortfolioPoint] = []


class FactorICResult(BaseModel):
    ready: bool
    factor: str
    hold_days: int
    sample_count: int           # 有效采样时点数
    mean_ic: float = 0.0        # 平均 rank IC（客观符号，随因子方向）
    ic_ir: float = 0.0          # IC 信息比率 = mean/std
    ic_win_rate: float = 0.0    # IC > 0 的时点占比
    long_short: float = 0.0     # 多空收益（按因子方向对齐，>0 有效）
    quantiles: list[QuantileReturn] = []
