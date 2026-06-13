"""VWAP 偏离回归策略 — 量价加权均值回归（只做多）。

滚动 N 日 VWAP（成交量加权均价）= Σ(典型价 × 成交量) / Σ(成交量)，
典型价 = (最高 + 最低 + 收盘) / 3。VWAP 是机构成本线的代理，
价格大幅低于 VWAP 视为「相对放量成本超跌」，回归概率高。

入场：收盘 < VWAP × (1 - bias_pct) → 超跌买入
出场：收盘 ≥ VWAP（回到加权成本线上方）→ 平多

这是策略库里唯一的「成交量加权价格」范式 —— 普通均线等权，VWAP 让
放量交易日的价格权重更高，更贴近真实平均持仓成本。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class VwapBiasParams(BaseParams):
    period: int = Field(default=20, title="VWAP 周期", ge=2, le=120)
    bias_pct: float = Field(default=0.05, title="超跌偏离阈值", ge=0.005, le=0.5)


class VwapBiasState(BaseState):
    vwap: float = Field(default=0.0, title="VWAP")
    bias: float = Field(default=0.0, title="偏离率")


class VwapBiasStrategy(StrategyBase):
    """价格跌破 VWAP×(1-bias) 超跌买入 / 回到 VWAP 上方卖出（只做多）。"""

    author = "tcalpha"
    params: VwapBiasParams = VwapBiasParams()
    state: VwapBiasState = VwapBiasState()
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

        n = self.params.period
        typical = (self.am.high[-n:] + self.am.low[-n:] + self.am.close[-n:]) / 3
        vol = self.am.volume[-n:]
        vol_sum = float(vol.sum())
        if vol_sum <= 0:
            return
        vwap = float((typical * vol).sum() / vol_sum)
        self.state.vwap = vwap

        close = bar.close_price
        self.state.bias = close / vwap - 1 if vwap > 0 else 0.0

        if self.state.pos == 0 and close < vwap * (1 - self.params.bias_pct):
            self.vars.direction = 1
            self.vars.strength = min(int(abs(self.state.bias) / self.params.bias_pct * 50), 100)
            self.vars.tip = f"跌破 VWAP({vwap:.2f}) {self.state.bias:.1%}，超跌买入"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and close >= vwap:
            self.vars.direction = -1
            self.vars.strength = 60
            self.vars.tip = f"回到 VWAP({vwap:.2f}) 上方，卖出"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
