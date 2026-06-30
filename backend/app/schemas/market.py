"""行情 DTO（Phase 1）。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    code: str
    exchange: str
    name: str
    industry: str | None = None
    list_date: date | None = None
    is_active: bool


class SymbolListResponse(BaseModel):
    items: list[SymbolOut]
    total: int


class KlineBar(BaseModel):
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


class KlineResponse(BaseModel):
    symbol: str
    period: str
    bars: list[KlineBar]
    total: int


class DownloadTriggerResponse(BaseModel):
    symbol: str
    task_id: str
    message: str = Field(default="download task submitted")


class RefreshTriggerResponse(BaseModel):
    task_id: str
    message: str = Field(default="refresh task submitted")


class SentimentOut(BaseModel):
    """市场情绪温度计（实时聚合自全市场 spot 快照）。"""

    ready: bool
    total: int = 0
    up: int = 0
    down: int = 0
    flat: int = 0
    limit_up: int = 0
    limit_down: int = 0
    adv_decline_ratio: float = 0.0  # 涨跌比 = 上涨/下跌
    profit_effect: float = 0.0      # 赚钱效应 = 上涨/总数
    avg_pct_chg: float = 0.0        # 全市场平均涨跌幅
    temperature: int = 50           # 情绪温度 0-100（上涨/活跃 ×100）


class SentimentPoint(BaseModel):
    """情绪历史曲线点（每日一条）。"""

    date: str
    temperature: int
    up: int = 0
    down: int = 0
    limit_up: int = 0
    limit_down: int = 0


class LadderBucket(BaseModel):
    label: str   # 1板 / 2板 / 3板 / 4板+
    count: int


class LimitUpLeader(BaseModel):
    symbol: str
    code: str
    name: str
    boards: int


class LimitUpLadder(BaseModel):
    """连板梯队（全市场打板情绪高度）。"""

    ready: bool
    total: int = 0        # 涨停（含连板）家数
    max_board: int = 0    # 最高连板高度
    ladder: list[LadderBucket] = []
    leaders: list[LimitUpLeader] = []
