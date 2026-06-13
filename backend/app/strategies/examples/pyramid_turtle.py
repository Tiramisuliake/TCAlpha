"""金字塔加仓海龟策略 — 突破入场 + 顺势分批加仓（只做多）。

海龟交易法则的精髓之一：突破后不是一次满仓，而是随趋势确认逐步加码。

入场：收盘突破前 entry_window 日最高 → 开首仓（1 unit）
加仓：持仓中、未达 max_units，且收盘较「上次加仓价」再涨 add_step × ATR
      → 再加 1 unit（金字塔，每层间距按波动率自适应）
出场：收盘跌破前 exit_window 日最低 → 一次性全平

这是策略库里唯一的「仓位管理 / 分批建仓」范式 —— 其余策略都是一次性
开满仓。引擎 `_match_orders` 的 open 分支对持仓累加无上限，天然支持多次加仓；
单根 bar 仅发一个信号（开首仓与加仓不会同 bar 触发）。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase

_UNIT = 100  # 每个 unit 的股数（A 股一手）


class PyramidTurtleParams(BaseParams):
    entry_window: int = Field(default=20, title="入场窗口(日新高)", ge=5, le=120)
    exit_window: int = Field(default=10, title="出场窗口(日新低)", ge=3, le=120)
    atr_period: int = Field(default=14, title="ATR 周期", ge=2, le=100)
    add_step: float = Field(default=0.5, title="加仓间距(×ATR)", ge=0.1, le=5.0)
    max_units: int = Field(default=4, title="最大仓位单元数", ge=1, le=10)


class PyramidTurtleState(BaseState):
    entry_high: float = Field(default=0.0, title="入场上轨(前N日高)")
    exit_low: float = Field(default=0.0, title="出场下轨(前M日低)")
    atr: float = Field(default=0.0, title="ATR")
    last_add_price: float = Field(default=0.0, title="上次加仓价")


class PyramidTurtleStrategy(StrategyBase):
    """唐奇安突破开首仓 + 顺势金字塔加仓 + 跌破下轨全平（只做多）。"""

    author = "tcalpha"
    params: PyramidTurtleParams = PyramidTurtleParams()
    state: PyramidTurtleState = PyramidTurtleState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        size = max(self.params.entry_window, self.params.exit_window, self.params.atr_period) + 10
        self.am = ArrayManager(size=max(size, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        ew, xw = self.params.entry_window, self.params.exit_window
        entry_high = float(self.am.high[-ew - 1 : -1].max())  # 前 N 日（不含当前）
        exit_low = float(self.am.low[-xw - 1 : -1].min())
        atr = float(self.am.atr(self.params.atr_period))
        self.state.entry_high = entry_high
        self.state.exit_low = exit_low
        self.state.atr = atr

        close = bar.close_price
        pos = self.state.pos
        units = pos // _UNIT

        if pos == 0:
            # 空仓：突破前 N 日高开首仓
            if close > entry_high:
                self.state.last_add_price = close
                self.vars.direction = 1
                self.vars.strength = 70
                self.vars.tip = f"突破{ew}日高 {entry_high:.2f}，开首仓（ATR={atr:.2f}）"
                self.vars.suggest_price = close
                self.vars.allow_open_long = True
                self.vars.allow_open_short = False
                self._pending_signal = ("long", "open", _UNIT)
            return

        # 持仓中：先判出场（跌破下轨全平），否则判加仓
        if close < exit_low:
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"跌破{xw}日低 {exit_low:.2f}，全平 {units} 仓"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", pos)
        elif units < self.params.max_units and atr > 0 and (
            close >= self.state.last_add_price + self.params.add_step * atr
        ):
            self.state.last_add_price = close
            self.vars.direction = 1
            self.vars.strength = min(60 + units * 10, 100)
            self.vars.tip = f"顺势加第 {units + 1} 仓 @ {close:.2f}"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", _UNIT)
