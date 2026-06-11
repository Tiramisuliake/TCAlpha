"""趋势回踩策略 — 上升趋势中买回调（只做多）。

趋势过滤：收盘站上长均线（trend_window）才允许入场
入场：当日最低触及/跌破短均线（pull_window）且收盘收回其上 —— 回踩企稳
出场：收盘跌破长均线（趋势走坏）

与海龟 / ATR 止损的「追突破」相反，这是 A 股实战最常用的「趋势中
低吸」范式：突破追高容易买在波段顶，回踩企稳再上车成本更优；
代价是强趋势不回头时会踏空。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class PullbackParams(BaseParams):
    trend_window: int = Field(default=60, title="趋势均线周期", ge=10, le=250)
    pull_window: int = Field(default=20, title="回踩均线周期", ge=2, le=120)


class PullbackState(BaseState):
    trend_ma: float = Field(default=0.0, title="趋势均线")
    pull_ma: float = Field(default=0.0, title="回踩均线")


class PullbackStrategy(StrategyBase):
    """上升趋势回踩短均线企稳买入 / 跌破趋势线卖出（只做多）。"""

    author = "tcalpha"
    params: PullbackParams = PullbackParams()
    state: PullbackState = PullbackState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        size = max(self.params.trend_window, self.params.pull_window) + 10
        self.am = ArrayManager(size=max(size, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        trend_ma = float(self.am.sma(self.params.trend_window, array=False))
        pull_ma = float(self.am.sma(self.params.pull_window, array=False))
        self.state.trend_ma = trend_ma
        self.state.pull_ma = pull_ma

        close = bar.close_price
        uptrend = close > trend_ma
        touched = bar.low_price <= pull_ma  # 盘中回踩到短均线
        reclaimed = close >= pull_ma        # 收盘收回均线上方（企稳）

        if self.state.pos == 0 and uptrend and touched and reclaimed:
            self.vars.direction = 1
            self.vars.strength = 70
            self.vars.tip = f"回踩 MA{self.params.pull_window}({pull_ma:.2f}) 企稳，买入"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and close < trend_ma:
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"跌破趋势线 MA{self.params.trend_window}({trend_ma:.2f})，卖出"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
