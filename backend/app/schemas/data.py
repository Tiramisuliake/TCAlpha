"""数据管理 DTO。"""
from __future__ import annotations

from pydantic import BaseModel


class SyncFailure(BaseModel):
    symbol: str
    period: str
    error: str
    updated_at: str | None = None


class DataHealthOut(BaseModel):
    """数据健康面板：覆盖度 + 同步状态。"""

    symbols_total: int          # PG symbols 活跃总数
    bar1d_covered: int          # ArcticDB bar_1d 实际有数据的标的数
    coverage_rate: float        # bar1d_covered / symbols_total
    sync_ok: int                # SyncLog 成功条数
    sync_failed: int            # SyncLog 失败条数
    recent_failures: list[SyncFailure] = []
