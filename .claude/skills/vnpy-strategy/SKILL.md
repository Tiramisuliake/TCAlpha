---
name: vnpy-strategy
description: 策略开发 / 三层 Params/State/Vars / vnpy BarData/ArrayManager 复用 / 信号生成。触发词：策略、strategy、CTA、信号、BarData、ArrayManager、vnpy、Params、State、Vars
---

# 策略开发

## 三层数据模型（沿用观澜）

| 层 | 用途 | 持久化 |
|---|---|---|
| `Params` | 用户可调参数 | ✅ |
| `State` | 策略运行状态 | ✅ |
| `Vars` | 向 UI 输出信号 | ❌ |

基类在 `app/strategies/base.py`。

## 策略类模板

```python
from pydantic import Field
from app.strategies.base import BaseParams, BaseState, BaseVars, StrategyBase


class MacdParams(BaseParams):
    fast: int = Field(default=12, ge=2, le=100, title="快线周期")
    slow: int = Field(default=26, ge=5, le=200, title="慢线周期")
    signal: int = Field(default=9, ge=2, le=50, title="信号周期")
    strength_scale: float = Field(default=5.0, ge=0.1, le=100.0, title="强度缩放")


class MacdState(BaseState):
    macd: float = Field(default=0.0, title="MACD")
    signal_val: float = Field(default=0.0, title="Signal")
    hist: float = Field(default=0.0, title="柱状图")
    macd_prev: float = Field(default=0.0)
    signal_prev: float = Field(default=0.0)


class MacdStrategy(StrategyBase):
    """MACD 金叉死叉策略 — 兼容自动 + 辅助交易"""
    author = "tcalpha"
    params: MacdParams = MacdParams()
    state: MacdState = MacdState()
    vars: BaseVars = BaseVars()

    def __init__(self, symbol: str, params: dict | None = None):
        super().__init__(symbol, params)
        from vnpy.trader.utility import ArrayManager
        self.am = ArrayManager(size=100)

    def on_bar(self, bar) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        macd, sig, hist = self.am.macd(self.params.fast, self.params.slow, self.params.signal)

        self.state.macd_prev = self.state.macd
        self.state.signal_prev = self.state.signal_val
        self.state.macd = macd
        self.state.signal_val = sig
        self.state.hist = hist

        cross_up = self.state.macd > self.state.signal_val and self.state.macd_prev <= self.state.signal_prev
        cross_dn = self.state.macd < self.state.signal_val and self.state.macd_prev >= self.state.signal_prev

        strength = min(int(abs(hist) * self.params.strength_scale), 100)
        if hist > 0:
            self.vars.direction = 1
            self.vars.strength = strength
            self.vars.tip = f"MACD 金叉 hist={hist:.2f}" if cross_up else f"多头 hist={hist:.2f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = True
            self.vars.allow_open_short = False
        elif hist < 0:
            self.vars.direction = -1
            self.vars.strength = strength
            self.vars.tip = f"MACD 死叉 hist={hist:.2f}" if cross_dn else f"空头 hist={hist:.2f}"
            self.vars.suggest_price = bar.close_price
            self.vars.allow_open_long = False
            self.vars.allow_open_short = True

        # 信号 → 落库 / 推送（runtime 帮忙做）
```

## vnpy 复用清单

| 用 | 模块 |
|---|---|
| `BarData` / `TickData` | `vnpy.trader.object` |
| `ArrayManager`（OHLCV 缓冲 + 内置 MA/MACD/RSI/BOLL 等） | `vnpy.trader.utility` |
| `BarGenerator`（tick → bar 聚合） | `vnpy.trader.utility` |
| `CtaTemplate`（如需深度集成） | `vnpy.app.cta_strategy.template` |

**不用** vnpy 的 EventEngine / MainEngine / Gateway / CtaEngine（那些是桌面架构），TCAlpha 用 Celery + 自己的 runtime。

## 把 K 线 → BarData

```python
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval

def df_to_bars(df, symbol: str):
    exchange = Exchange.SSE if symbol.startswith("sh") else Exchange.SZSE
    for ts, row in df.iterrows():
        yield BarData(
            symbol=symbol[2:], exchange=exchange,
            datetime=ts.to_pydatetime(),
            interval=Interval.DAILY,
            open_price=row.open, high_price=row.high,
            low_price=row.low, close_price=row.close,
            volume=row.volume, turnover=row.get("amount", 0),
            gateway_name="TCALPHA",
        )
```

## 策略生命周期

1. 实例化：`s = MacdStrategy("sh600000", params={...})`
2. 加载历史（回测/初始化）：`for bar in df_to_bars(df, s.symbol): s.on_bar(bar)`
3. 实时（Phase 4）：Celery 长跑任务 + AKShare 拉取 + 调用 `on_bar`
4. 状态持久化：`json.dumps(s.state.model_dump())` 存到 `strategy_configs.state`

## 注册到 service 层

```python
# app/services/strategy.py
from app.strategies.examples.ma_cross import MaCrossStrategy
from app.strategies.examples.macd import MacdStrategy

STRATEGY_CLASSES = {
    "MaCrossStrategy": MaCrossStrategy,
    "MacdStrategy": MacdStrategy,
}

def instantiate(class_name: str, symbol: str, params: dict):
    cls = STRATEGY_CLASSES.get(class_name)
    if not cls:
        raise ValueError(f"unknown strategy class: {class_name}")
    return cls(symbol, params)
```

新策略加进 `STRATEGY_CLASSES`。

## 测试模式

- **回测**：backtest_engine 加载 ArcticDB 历史 → 逐条 `on_bar` → 收集成交
- **辅助**：长跑 task + AKShare 实时分钟 → `on_bar` → 把 `vars` 推 Redis pub/sub
- **模拟自动**：vars 满足开仓条件 → SimGateway 落 order

## 禁止

- ❌ 在 `on_bar` 里调 IO（网络/DB）—— 必须纯内存计算
- ❌ 改 `Params` 字段（参数是用户的）
- ❌ 策略类有 Qt 依赖（必须纯 Python）
- ❌ 用 vnpy CtaEngine（用 TCAlpha runtime）
