"""网格交易策略 — 震荡市低买高卖（只做多）。

以首根 bar 收盘价为锚（基准价），价格每跌 grid_pct 一格买入 100 股，
每涨回一格卖出 100 股，最多持有 max_grids 格。

目标格数 = floor((锚 - 收盘) / (锚 × grid_pct))，截到 [0, max_grids]；
当前格数由实际持仓推导（pos // 100），涨跌停 / 停牌导致未成交时
不会与真实仓位漂移。每根 bar 只挂一格的单（撮合在下一根开盘）。
"""
from __future__ import annotations

import math

from pydantic import Field

from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase

_GRID_VOLUME = 100  # 每格股数（A 股一手）


class GridParams(BaseParams):
    grid_pct: float = Field(default=0.05, title="网格间距(比例)", ge=0.005, le=0.5)
    max_grids: int = Field(default=5, title="最大格数", ge=1, le=20)


class GridState(BaseState):
    anchor: float = Field(default=0.0, title="基准价(锚)")
    target_level: int = Field(default=0, title="目标格数")


class GridStrategy(StrategyBase):
    """网格交易：跌一格买、涨一格卖（只做多）。"""

    author = "tcalpha"
    params: GridParams = GridParams()
    state: GridState = GridState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None) -> None:
        super().__init__(symbol, params)
        self._pending_signal: tuple[str, str, int] | None = None

    def on_bar(self, bar) -> None:  # bar: vnpy BarData
        self._pending_signal = None
        close = bar.close_price

        # 首根 bar 锚定基准价，不交易
        if self.state.anchor <= 0:
            self.state.anchor = close
            return

        step = self.state.anchor * self.params.grid_pct
        target = math.floor((self.state.anchor - close) / step) if step > 0 else 0
        target = max(0, min(target, self.params.max_grids))
        self.state.target_level = target

        level = self.state.pos // _GRID_VOLUME

        if target > level:
            # 价格跌到更深的格 → 补一格
            self.vars.direction = 1
            self.vars.strength = min(int(target / self.params.max_grids * 100), 100)
            self.vars.tip = f"跌至第 {target} 格（锚 {self.state.anchor:.2f}），买入一格"
            self.vars.suggest_price = close
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "open", _GRID_VOLUME)
        elif target < level and self.state.pos > 0:
            # 价格涨回上方的格 → 卖一格
            self.vars.direction = -1
            self.vars.strength = min(int((level - target) / self.params.max_grids * 100), 100)
            self.vars.tip = f"涨回第 {target} 格（持 {level} 格），卖出一格"
            self.vars.suggest_price = close
            self.vars.allow_open_long = False
            self.vars.allow_open_short = False
            self._pending_signal = ("long", "close", _GRID_VOLUME)
        else:
            self.vars.direction = 0
            self.vars.strength = 0
            self.vars.tip = f"持 {level}/{target} 格，观望"
            self.vars.suggest_price = close
