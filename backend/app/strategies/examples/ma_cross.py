"""MA 均线交叉策略 — 示例（Phase 3 完整实现）。"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class MaCrossParams(BaseParams):
    fast: int = Field(default=10, title="快线周期", ge=2, le=200)
    slow: int = Field(default=20, title="慢线周期", ge=2, le=500)


class MaCrossState(BaseState):
    fast_ma: float = Field(default=0.0, title="快线值")
    slow_ma: float = Field(default=0.0, title="慢线值")
    fast_prev: float = Field(default=0.0)
    slow_prev: float = Field(default=0.0)


class MaCrossStrategy(StrategyBase):
    """MA 均线交叉策略示例。"""

    author = "tcalpha"
    params: MaCrossParams = MaCrossParams()
    state: MaCrossState = MaCrossState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        self.am = ArrayManager(size=max(self.params.slow + 10, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        self.state.fast_prev = self.state.fast_ma
        self.state.slow_prev = self.state.slow_ma
        self.state.fast_ma = float(self.am.sma(self.params.fast, array=False))
        self.state.slow_ma = float(self.am.sma(self.params.slow, array=False))

        fast, slow = self.state.fast_ma, self.state.slow_ma
        fast_prev, slow_prev = self.state.fast_prev, self.state.slow_prev

        cross_up = fast > slow and fast_prev <= slow_prev
        cross_dn = fast < slow and fast_prev >= slow_prev

        if cross_up and self.state.pos == 0:
            self.vars.direction = 1
            self.vars.strength = 80
            self.vars.tip = f"金叉 fast={fast:.2f} slow={slow:.2f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            # 通知引擎：开多
            self._pending_signal = ("long", "open", 100)
        elif cross_dn and self.state.pos > 0:
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"死叉 fast={fast:.2f} slow={slow:.2f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = True
            self._pending_signal = ("long", "close", self.state.pos)
        else:
            self._pending_signal = None
