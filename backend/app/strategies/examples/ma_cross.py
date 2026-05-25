"""MA 均线交叉策略 — 示例（Phase 3 完整实现）。"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, StrategyBase


class MaCrossParams(BaseParams):
    fast: int = Field(default=10, title="快线周期", ge=2, le=200)
    slow: int = Field(default=20, title="慢线周期", ge=2, le=500)


class MaCrossState(BaseState):
    fast_ma: float = Field(default=0.0, title="快线值")
    slow_ma: float = Field(default=0.0, title="慢线值")


class MaCrossStrategy(StrategyBase):
    """MA 均线交叉策略示例。"""
    author = "tcalpha"
    params: MaCrossParams = MaCrossParams()
    state: MaCrossState = MaCrossState()
