"""布林带均值回归策略 — 跌破下轨买入 / 升破上轨卖出（只做多）。"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class BollParams(BaseParams):
    period: int = Field(default=20, title="布林周期", ge=2, le=200)
    dev: float = Field(default=2.0, title="标准差倍数", ge=0.5, le=5.0)


class BollState(BaseState):
    boll_up: float = Field(default=0.0, title="上轨")
    boll_mid: float = Field(default=0.0, title="中轨")
    boll_down: float = Field(default=0.0, title="下轨")


class BollStrategy(StrategyBase):
    """布林带均值回归：收盘跌破下轨买入，升破上轨卖出（只做多）。"""

    author = "tcalpha"
    params: BollParams = BollParams()
    state: BollState = BollState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        self.am = ArrayManager(size=max(self.params.period + 10, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        up, down = self.am.boll(self.params.period, self.params.dev, array=False)
        mid = float(self.am.sma(self.params.period, array=False))
        self.state.boll_up = float(up)
        self.state.boll_mid = mid
        self.state.boll_down = float(down)

        close = bar.close_price
        if close <= self.state.boll_down and self.state.pos == 0:
            # 跌破下轨 → 开多
            self.vars.direction = 1
            self.vars.strength = 75
            self.vars.tip = f"跌破下轨 {down:.2f}，买入"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif close >= self.state.boll_up and self.state.pos > 0:
            # 升破上轨 → 平多
            self.vars.direction = -1
            self.vars.strength = 75
            self.vars.tip = f"升破上轨 {up:.2f}，卖出"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
