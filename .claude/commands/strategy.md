# /strategy — 创建一个新策略类

在 `backend/app/strategies/examples/` 下生成一个完整策略：Params / State / Vars + on_bar 骨架，并注册到 `STRATEGY_CLASSES`。

## 流程

1. 问：策略名（PascalCase 类名 + 中文描述）+ 用什么指标 + 关键参数

2. 写 `backend/app/strategies/examples/<x>.py`：

```python
from pydantic import Field
from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class XxxParams(BaseParams):
    # 参数列表，带 Field(title="中文名", ge=..., le=...)
    ...


class XxxState(BaseState):
    # 中间状态（持仓继承自基类的 pos）
    ...


class XxxStrategy(StrategyBase):
    """<中文描述>"""
    author = "..."
    params: XxxParams = XxxParams()
    state: XxxState = XxxState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None):
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager
        self.am = ArrayManager(size=100)

    def on_bar(self, bar) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        # 1. 计算指标
        # 2. 更新 state
        # 3. 计算信号 → 写 vars
```

3. 注册到 `backend/app/services/strategy.py` 的 `STRATEGY_CLASSES`

4. 写最小测试 `backend/tests/test_strategy_<x>.py`：
   - 构造 fake bars
   - 喂进策略
   - 断言 state / vars 关键字段

5. 跑 `cd backend && uv run pytest tests/test_strategy_<x>.py`

## 约束

- 必须三层 Params / State / Vars
- on_bar 纯计算，不能 IO
- 至少 1 个测试用例
