"""布林收口突破策略 — 波动率挤压后的爆发（只做多）。

挤压判定：**前一根 bar** 的带宽 (上轨-下轨)/中轨 ≤ squeeze_th
（突破当根带宽已被拉开，须看突破前的收口状态）
入场：处于挤压状态且收盘突破上轨 → 开多
出场：收盘跌破中轨 → 平多

与 BollStrategy（均值回归：跌破下轨买）是同一指标的相反范式：
长时间横盘把波动率压缩到极致后，突破方向往往孕育一段趋势行情。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class BollSqueezeParams(BaseParams):
    period: int = Field(default=20, title="布林周期", ge=2, le=200)
    dev: float = Field(default=2.0, title="标准差倍数", ge=0.5, le=5.0)
    squeeze_th: float = Field(default=0.10, title="挤压带宽阈值", ge=0.01, le=0.5)


class BollSqueezeState(BaseState):
    boll_up: float = Field(default=0.0, title="上轨")
    boll_mid: float = Field(default=0.0, title="中轨")
    boll_down: float = Field(default=0.0, title="下轨")
    bandwidth: float = Field(default=0.0, title="带宽")
    bandwidth_prev: float = Field(default=0.0)


class BollSqueezeStrategy(StrategyBase):
    """布林收口（波动率挤压）后突破上轨开多 / 跌破中轨平多（只做多）。"""

    author = "tcalpha"
    params: BollSqueezeParams = BollSqueezeParams()
    state: BollSqueezeState = BollSqueezeState()
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
        self.state.bandwidth_prev = self.state.bandwidth
        self.state.bandwidth = (float(up) - float(down)) / mid if mid > 0 else 0.0

        close = bar.close_price
        squeezed = 0 < self.state.bandwidth_prev <= self.params.squeeze_th

        if self.state.pos == 0 and squeezed and close > float(up):
            self.vars.direction = 1
            self.vars.strength = 85
            self.vars.tip = (
                f"收口（带宽 {self.state.bandwidth_prev:.1%}）后突破上轨 {float(up):.2f}，买入"
            )
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and close < mid:
            self.vars.direction = -1
            self.vars.strength = 75
            self.vars.tip = f"跌破中轨 {mid:.2f}，卖出"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
