"""海龟唐奇安通道突破策略 — 趋势跟踪经典。

入场：收盘突破前 entry_window 日最高 → 开多
出场：收盘跌破前 exit_window 日最低 → 平多

用「前 N 日」通道（不含当前 bar），否则当前 bar 的 high 必然 ≤ 含自身的通道上轨，
突破判断恒为假。next-bar-open 撮合下用收盘突破，过滤日内假突破。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class TurtleParams(BaseParams):
    entry_window: int = Field(default=20, title="入场窗口(日新高)", ge=5, le=120)
    exit_window: int = Field(default=10, title="出场窗口(日新低)", ge=3, le=120)


class TurtleState(BaseState):
    entry_high: float = Field(default=0.0, title="入场上轨(前N日高)")
    exit_low: float = Field(default=0.0, title="出场下轨(前M日低)")


class TurtleStrategy(StrategyBase):
    """海龟唐奇安通道突破策略。"""

    author = "tcalpha"
    params: TurtleParams = TurtleParams()
    state: TurtleState = TurtleState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        size = max(self.params.entry_window, self.params.exit_window) + 10
        self.am = ArrayManager(size=max(size, 30))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        ew = self.params.entry_window
        xw = self.params.exit_window
        # 前 N/M 日通道（切片不含当前 bar）
        entry_high = float(self.am.high[-ew - 1 : -1].max())
        exit_low = float(self.am.low[-xw - 1 : -1].min())
        self.state.entry_high = entry_high
        self.state.exit_low = exit_low

        close = bar.close_price

        if self.state.pos == 0 and close > entry_high:
            self.vars.direction = 1
            self.vars.strength = 80
            self.vars.tip = f"突破{ew}日新高 {entry_high:.2f}，开多"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and close < exit_low:
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"跌破{xw}日新低 {exit_low:.2f}，平多"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = True
            self._pending_signal = ("long", "close", self.state.pos)
        else:
            self._pending_signal = None
