"""策略基类 — 沿用观澜的三层数据模型（Params / State / Vars）。

只是去掉了 PySide6 / EventEngine 依赖，纯 Pydantic。
后期 Phase 3 由 backtest_engine 和 strategy_tasks 驱动 on_bar。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseParams(BaseModel):
    """策略参数 — 用户可调，持久化保存。"""
    model_config = ConfigDict(validate_assignment=True)


class BaseState(BaseModel):
    """运行状态 — 策略计算中间值，持久化保存。"""
    model_config = ConfigDict(validate_assignment=True)
    pos: int = Field(default=0, title="持仓")


class BaseVars(BaseModel):
    """临时变量 — 向 UI 输出信号，不持久化。"""
    model_config = ConfigDict(validate_assignment=True)
    direction: int = Field(default=0, title="方向", description="1 多 / -1 空 / 0 中性")
    strength: int = Field(default=0, title="强度", ge=0, le=100)
    tip: str = Field(default="", title="提示")
    suggest_price: float = Field(default=0.0, title="建议价")
    allow_open_long: bool = Field(default=False, title="允许开多")
    allow_open_short: bool = Field(default=False, title="允许开空")


class StrategyBase:
    """策略基类（不继承 vnpy CtaTemplate，由 runtime 桥接 BarData / ArrayManager）。

    子类只需重写 on_bar(bar)。
    """

    author: str = ""
    params: BaseParams
    state: BaseState
    vars: BaseVars

    def __init__(self, symbol: str, params: dict[str, Any] | None = None) -> None:
        self.symbol = symbol
        # 类上的 params/state/vars 仅作“默认模板”，这里为每个实例深拷贝一份，
        # 否则所有实例共享同一个类属性单例，会导致跨回测 / 多策略状态污染。
        cls = type(self)
        self.params = cls.params.model_copy(deep=True)
        self.state = cls.state.model_copy(deep=True)
        self.vars = cls.vars.model_copy(deep=True)
        if params:
            for k, v in params.items():
                setattr(self.params, k, v)

    def on_bar(self, bar: Any) -> None:  # bar: vnpy BarData
        raise NotImplementedError
