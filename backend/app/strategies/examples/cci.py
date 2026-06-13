"""CCI 顺势指标策略 — 超买超卖区穿越（只做多）。

CCI（Commodity Channel Index）衡量价格偏离统计均值的程度，常用 ±100 分界：
> +100 视为强势/超买区，< -100 视为弱势/超卖区。

入场：CCI 从超卖区（< -100）向上穿越 -100 → 抄底开多（下跌动能衰竭、回升确立）
出场：CCI 从超买区（> +100）向下穿越 +100 → 高位平多（涨势见顶回落）

与 RSI/KDJ 同属超买超卖范式，但 CCI 无界（可远超 ±100）、对趋势加速更敏感，
是独立常用的「顺势」指标。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class CciParams(BaseParams):
    period: int = Field(default=20, title="CCI 周期", ge=2, le=100)
    oversold: float = Field(default=-100.0, title="超卖线", ge=-300, le=-20)
    overbought: float = Field(default=100.0, title="超买线", ge=20, le=300)


class CciState(BaseState):
    cci: float = Field(default=0.0, title="CCI 值")
    cci_prev: float = Field(default=0.0)


class CciStrategy(StrategyBase):
    """CCI 顺势：超卖区上穿 -100 买入、超买区下穿 +100 卖出（只做多）。"""

    author = "tcalpha"
    params: CciParams = CciParams()
    state: CciState = CciState()
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

        cci = float(self.am.cci(self.params.period))
        self.state.cci_prev = self.state.cci
        self.state.cci = cci
        prev = self.state.cci_prev

        cross_up = cci > self.params.oversold and prev <= self.params.oversold
        cross_dn = cci < self.params.overbought and prev >= self.params.overbought

        if self.state.pos == 0 and cross_up:
            self.vars.direction = 1
            self.vars.strength = min(int(50 + abs(cci - self.params.oversold)), 100)
            self.vars.tip = f"CCI={cci:.0f} 上穿超卖线，买入"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and cross_dn:
            self.vars.direction = -1
            self.vars.strength = min(int(50 + abs(cci - self.params.overbought)), 100)
            self.vars.tip = f"CCI={cci:.0f} 下穿超买线，卖出"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
