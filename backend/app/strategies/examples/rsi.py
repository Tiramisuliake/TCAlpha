"""RSI 超卖买入 / 超买卖出策略 — 均值回归示例（只做多）。"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class RsiParams(BaseParams):
    period: int = Field(default=14, title="RSI 周期", ge=2, le=100)
    oversold: float = Field(default=30.0, title="超卖阈值", ge=1, le=49)
    overbought: float = Field(default=70.0, title="超买阈值", ge=51, le=99)


class RsiState(BaseState):
    rsi: float = Field(default=0.0, title="RSI 值")


class RsiStrategy(StrategyBase):
    """RSI 均值回归：RSI 跌破超卖线买入，升破超买线卖出（只做多）。"""

    author = "tcalpha"
    params: RsiParams = RsiParams()
    state: RsiState = RsiState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        self.am = ArrayManager(size=max(self.params.period * 2, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        rsi = float(self.am.rsi(self.params.period, array=False))
        self.state.rsi = rsi

        if rsi <= self.params.oversold and self.state.pos == 0:
            # 超卖 → 开多
            self.vars.direction = 1
            self.vars.strength = min(int(50 + (self.params.oversold - rsi) * 2), 100)
            self.vars.tip = f"RSI={rsi:.1f} 超卖，买入"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif rsi >= self.params.overbought and self.state.pos > 0:
            # 超买 → 平多
            self.vars.direction = -1
            self.vars.strength = min(int(50 + (rsi - self.params.overbought) * 2), 100)
            self.vars.tip = f"RSI={rsi:.1f} 超买，卖出"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
