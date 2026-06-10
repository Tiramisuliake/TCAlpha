"""KDJ 随机指标策略 — A 股口径手工递推（只做多）。

RSV = (C - LLV(low,n)) / (HHV(high,n) - LLV(low,n)) × 100
K = 2/3·K' + 1/3·RSV，D = 2/3·D' + 1/3·K，J = 3K - 2D（K/D 初值 50）

talib STOCH 的平滑方式与 A 股软件的 1/3 递推口径不同，故自算；
K/D 放 State 持久化，重启续算不漂移。

入场：K 上穿 D（金叉）且 K 处低位 → 开多
出场：K 下穿 D（死叉）且 K 处高位 → 平多
"""
from __future__ import annotations

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class KdjParams(BaseParams):
    period: int = Field(default=9, title="RSV 周期", ge=2, le=60)
    buy_below: float = Field(default=30.0, title="低位线(金叉开多)", ge=5, le=49)
    sell_above: float = Field(default=70.0, title="高位线(死叉平多)", ge=51, le=95)


class KdjState(BaseState):
    k: float = Field(default=50.0, title="K 值")
    d: float = Field(default=50.0, title="D 值")
    j: float = Field(default=50.0, title="J 值")
    k_prev: float = Field(default=50.0)
    d_prev: float = Field(default=50.0)


class KdjStrategy(StrategyBase):
    """KDJ 低位金叉买入 / 高位死叉卖出（只做多）。"""

    author = "tcalpha"
    params: KdjParams = KdjParams()
    state: KdjState = KdjState()
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

        n = self.params.period
        hhv = float(self.am.high[-n:].max())
        llv = float(self.am.low[-n:].min())
        rsv = (bar.close_price - llv) / (hhv - llv) * 100 if hhv > llv else 50.0

        self.state.k_prev = self.state.k
        self.state.d_prev = self.state.d
        self.state.k = self.state.k_prev * 2 / 3 + rsv / 3
        self.state.d = self.state.d_prev * 2 / 3 + self.state.k / 3
        self.state.j = 3 * self.state.k - 2 * self.state.d

        k, d = self.state.k, self.state.d
        cross_up = k > d and self.state.k_prev <= self.state.d_prev
        cross_dn = k < d and self.state.k_prev >= self.state.d_prev

        if self.state.pos == 0 and cross_up and k < self.params.buy_below:
            self.vars.direction = 1
            self.vars.strength = min(int(50 + (self.params.buy_below - k) * 2), 100)
            self.vars.tip = f"KDJ 低位金叉 K={k:.1f} D={d:.1f}，买入"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", 100)
        elif self.state.pos > 0 and cross_dn and k > self.params.sell_above:
            self.vars.direction = -1
            self.vars.strength = min(int(50 + (k - self.params.sell_above) * 2), 100)
            self.vars.tip = f"KDJ 高位死叉 K={k:.1f} D={d:.1f}，卖出"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", self.state.pos)
