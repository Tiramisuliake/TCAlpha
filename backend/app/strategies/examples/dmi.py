"""DMI/ADX 趋势策略 — 方向 + 趋势强度双过滤（只做多）。

入场：+DI > -DI（多头方向）且 ADX ≥ 阈值（趋势够强）→ 开多
出场：-DI > +DI（方向反转）→ 平多

条件取「状态」而非「交叉沿」：交叉瞬间 ADX 往往尚未达标，等强度
确认后再进场不会错过趋势；ADX 闸门过滤震荡市方向线的频繁缠绕，
是 MA 交叉类策略的抗震荡升级版。指标走 vnpy ArrayManager（talib）。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class DmiParams(BaseParams):
    period: int = Field(default=14, title="DMI 周期", ge=2, le=100)
    adx_threshold: float = Field(default=25.0, title="ADX 趋势阈值", ge=5, le=60)


class DmiState(BaseState):
    adx: float = Field(default=0.0, title="ADX")
    plus_di: float = Field(default=0.0, title="+DI")
    minus_di: float = Field(default=0.0, title="-DI")


class DmiStrategy(StrategyBase):
    """DMI 方向交叉 + ADX 强度过滤（只做多）。"""

    author = "tcalpha"
    params: DmiParams = DmiParams()
    state: DmiState = DmiState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        self.am = ArrayManager(size=max(self.params.period * 3, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        n = self.params.period
        adx = float(self.am.adx(n))
        pdi = float(self.am.plus_di(n))
        mdi = float(self.am.minus_di(n))

        self.state.adx = adx
        self.state.plus_di = pdi
        self.state.minus_di = mdi

        if self.state.pos == 0 and pdi > mdi and adx >= self.params.adx_threshold:
            self.vars.direction = 1
            self.vars.strength = min(int(adx * 2), 100)
            self.vars.tip = f"+DI({pdi:.1f})>-DI({mdi:.1f}) 且 ADX={adx:.1f} 达标，开多"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and mdi > pdi:
            self.vars.direction = -1
            self.vars.strength = min(int(adx * 2), 100)
            self.vars.tip = f"-DI 反超 +DI（ADX={adx:.1f}），平多"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
