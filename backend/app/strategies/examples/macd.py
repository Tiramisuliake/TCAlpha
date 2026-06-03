"""MACD 金叉 / 死叉策略 — 趋势跟踪示例（只做多）。"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class MacdParams(BaseParams):
    fast: int = Field(default=12, title="快线周期", ge=2, le=100)
    slow: int = Field(default=26, title="慢线周期", ge=5, le=200)
    signal: int = Field(default=9, title="信号周期", ge=2, le=50)


class MacdState(BaseState):
    dif: float = Field(default=0.0, title="DIF")
    dea: float = Field(default=0.0, title="DEA")
    macd_hist: float = Field(default=0.0, title="MACD 柱")
    dif_prev: float = Field(default=0.0)
    dea_prev: float = Field(default=0.0)


class MacdStrategy(StrategyBase):
    """MACD：DIF 上穿 DEA（金叉）买入，下穿（死叉）卖出（只做多）。"""

    author = "tcalpha"
    params: MacdParams = MacdParams()
    state: MacdState = MacdState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        self.am = ArrayManager(size=max(self.params.slow + self.params.signal + 10, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        dif, dea, hist = self.am.macd(
            self.params.fast, self.params.slow, self.params.signal, array=False
        )
        self.state.dif_prev = self.state.dif
        self.state.dea_prev = self.state.dea
        self.state.dif = float(dif)
        self.state.dea = float(dea)
        self.state.macd_hist = float(hist)

        cross_up = self.state.dif > self.state.dea and self.state.dif_prev <= self.state.dea_prev
        cross_dn = self.state.dif < self.state.dea and self.state.dif_prev >= self.state.dea_prev

        if cross_up and self.state.pos == 0:
            # 金叉 → 开多
            self.vars.direction = 1
            self.vars.strength = 80
            self.vars.tip = f"MACD 金叉 DIF={dif:.3f} DEA={dea:.3f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif cross_dn and self.state.pos > 0:
            # 死叉 → 平多
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"MACD 死叉 DIF={dif:.3f} DEA={dea:.3f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
