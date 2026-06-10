"""ATR 吊灯止损策略 — 突破入场 + 跟踪止损出场（只做多）。

入场：收盘突破前 entry_window 日最高（不含当前 bar，同海龟）→ 开多
出场：吊灯止损 —— 持仓以来最高价 - atr_mult × ATR(atr_period)，
      收盘跌破止损线 → 平多

与海龟的区别在出场范式：海龟等「跌破前 M 日低」的信号出场，吊灯止损
随价格创新高把止损线**单调上移**锁住浮盈，回撤超过 atr_mult 倍波动率
即离场，趋势走完不吐回大部分利润。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class AtrStopParams(BaseParams):
    entry_window: int = Field(default=20, title="入场窗口(日新高)", ge=5, le=120)
    atr_period: int = Field(default=14, title="ATR 周期", ge=2, le=100)
    atr_mult: float = Field(default=3.0, title="止损倍数", ge=0.5, le=10)


class AtrStopState(BaseState):
    highest: float = Field(default=0.0, title="持仓最高价")
    stop_line: float = Field(default=0.0, title="吊灯止损线")
    atr: float = Field(default=0.0, title="ATR")


class AtrStopStrategy(StrategyBase):
    """突破开多 + ATR 吊灯跟踪止损（只做多）。"""

    author = "tcalpha"
    params: AtrStopParams = AtrStopParams()
    state: AtrStopState = AtrStopState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        size = max(self.params.entry_window, self.params.atr_period) + 10
        self.am = ArrayManager(size=max(size, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        atr = float(self.am.atr(self.params.atr_period))
        self.state.atr = atr
        close = bar.close_price

        if self.state.pos > 0:
            # 持仓：最高价只升不降 → 止损线单调上移
            self.state.highest = max(self.state.highest, bar.high_price)
            stop = self.state.highest - self.params.atr_mult * atr
            self.state.stop_line = max(self.state.stop_line, stop)
            if close < self.state.stop_line:
                self.vars.direction = -1
                self.vars.strength = 80
                self.vars.tip = f"跌破吊灯止损 {self.state.stop_line:.2f}（最高 {self.state.highest:.2f}），平多"
                self.vars.suggest_price = close
                self.vars.allow_open_long = False
                self.vars.allow_open_short = False
                self._pending_signal = ("long", "close", self.state.pos)
            return

        # 空仓：重置跟踪状态，等突破
        self.state.highest = 0.0
        self.state.stop_line = 0.0
        ew = self.params.entry_window
        entry_high = float(self.am.high[-ew - 1 : -1].max())
        if close > entry_high:
            self.vars.direction = 1
            self.vars.strength = 80
            self.vars.tip = f"突破{ew}日新高 {entry_high:.2f}，开多（ATR={atr:.2f}）"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
