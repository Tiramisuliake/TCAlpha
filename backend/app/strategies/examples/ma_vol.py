"""双均线 + 量能过滤策略 — 放量金叉才入场（只做多）。

入场：快线上穿慢线（金叉）且当根成交量 ≥ vol_ratio × 近 vol_window 日均量
出场：快线下穿慢线（死叉），出场不设量能门槛（离场宁早勿晚）

量能确认是 MaCross 的实战升级：无量金叉多为震荡市的假突破，
放量说明买盘真实进场，胜率显著高于裸均线交叉。
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class MaVolParams(BaseParams):
    fast: int = Field(default=5, title="快线周期", ge=2, le=200)
    slow: int = Field(default=20, title="慢线周期", ge=2, le=500)
    vol_window: int = Field(default=20, title="均量窗口", ge=2, le=120)
    vol_ratio: float = Field(default=1.5, title="放量倍数", ge=1.0, le=10)


class MaVolState(BaseState):
    fast_ma: float = Field(default=0.0, title="快线值")
    slow_ma: float = Field(default=0.0, title="慢线值")
    vol_ma: float = Field(default=0.0, title="均量")
    fast_prev: float = Field(default=0.0)
    slow_prev: float = Field(default=0.0)


class MaVolStrategy(StrategyBase):
    """放量金叉开多 / 死叉平多（只做多）。"""

    author = "tcalpha"
    params: MaVolParams = MaVolParams()
    state: MaVolState = MaVolState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager

        size = max(self.params.slow, self.params.vol_window) + 10
        self.am = ArrayManager(size=max(size, 50))
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self.am.update_bar(bar)
        self._pending_signal = None
        if not self.am.inited:
            return

        self.state.fast_prev = self.state.fast_ma
        self.state.slow_prev = self.state.slow_ma
        self.state.fast_ma = float(self.am.sma(self.params.fast, array=False))
        self.state.slow_ma = float(self.am.sma(self.params.slow, array=False))
        # 均量不含当前 bar：当根放量不抬高自己的基准
        self.state.vol_ma = float(self.am.volume[-self.params.vol_window - 1 : -1].mean())

        fast, slow = self.state.fast_ma, self.state.slow_ma
        cross_up = fast > slow and self.state.fast_prev <= self.state.slow_prev
        cross_dn = fast < slow and self.state.fast_prev >= self.state.slow_prev

        vol_ok = (
            self.state.vol_ma > 0
            and bar.volume >= self.params.vol_ratio * self.state.vol_ma
        )

        if cross_up and vol_ok and self.state.pos == 0:
            ratio = bar.volume / self.state.vol_ma
            self.vars.direction = 1
            self.vars.strength = min(int(50 + ratio * 10), 100)
            self.vars.tip = f"放量金叉（量比 {ratio:.1f}），开多"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif cross_up and not vol_ok and self.state.pos == 0:
            self.vars.direction = 0
            self.vars.strength = 30
            self.vars.tip = "金叉但无量，疑似假突破，观望"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
        elif cross_dn and self.state.pos > 0:
            self.vars.direction = -1
            self.vars.strength = 80
            self.vars.tip = f"死叉 fast={fast:.2f} slow={slow:.2f}，平多"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
