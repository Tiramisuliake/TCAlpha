---
name: backtest-engine
description: 回测引擎设计 / 撮合 / 收益曲线 / 最大回撤 / 夏普 / 手续费 / 滑点。触发词：回测、backtest、撮合、收益、回撤、夏普、Sharpe、引擎、性能指标
---

# 回测引擎

## 总体流程

```
BacktestJob (PG) 提交 → Celery task → 读 ArcticDB K 线
  → for bar: strategy.on_bar(bar) → 信号 → 撮合（next bar 开盘）
  → 收集 trade / pos → 结束算指标 → 写 PG (result + trades)
```

## 引擎结构

```
app/core/backtest_engine.py
├── run(job_id)                          # 主入口
├── _load_bars(symbol, start, end)       # 从 ArcticDB 读
├── _run_strategy(strategy, bars)        # 喂 bar
├── _match_orders(orders, next_bar)      # 撮合（用下一根开盘价）
├── _settle(trades, init_capital)        # 算资金曲线
└── _metrics(equity, trades)             # 算夏普/回撤/胜率
```

## 撮合规则（Phase 3 简单版）

- **下单时机**：策略 `on_bar` 结束后立即生成订单
- **成交时机**：下一根 K 线开盘价（避免未来函数）
- **手续费**：双边 `commission_rate * price * volume`（默认万 3）
- **印花税**：卖出额外 `0.001`（A 股规则）
- **滑点**：开盘价 ± `slippage`（默认 0.01 元）
- **不考虑停牌 / 涨跌停**：Phase 3 简化（Phase 4 加）

## 数据结构（中间）

```python
@dataclass
class PendingOrder:
    direction: str  # long / short
    offset: str     # open / close
    volume: int

@dataclass
class Trade:
    dt: datetime
    direction: str
    offset: str
    price: float
    volume: int
    commission: float
    pnl: float | None = None     # 平仓时填
```

## 指标计算

```python
import numpy as np
import pandas as pd

def metrics(equity: pd.Series, trades: list[Trade], init_capital: float) -> dict:
    rets = equity.pct_change().dropna()
    total_return = equity.iloc[-1] / init_capital - 1
    days = (equity.index[-1] - equity.index[0]).days
    annual_return = (1 + total_return) ** (252 / max(days, 1)) - 1 if days > 0 else 0

    downside = rets[rets < 0]
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    sortino = rets.mean() / downside.std() * np.sqrt(252) if len(downside) and downside.std() > 0 else 0

    cum_max = equity.cummax()
    drawdown = (equity - cum_max) / cum_max
    max_dd = drawdown.min()

    closed = [t for t in trades if t.pnl is not None]
    wins = [t for t in closed if t.pnl > 0]
    win_rate = len(wins) / len(closed) if closed else 0
    profit_factor = (
        sum(t.pnl for t in wins) / abs(sum(t.pnl for t in closed if t.pnl < 0))
        if any(t.pnl < 0 for t in closed) else float("inf")
    )

    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(max_dd),
        "trade_count": len(closed),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
    }
```

## Celery 任务集成

```python
# app/tasks/backtest_tasks.py
from app.core import backtest_engine
from app.tasks.celery_app import celery_app

@celery_app.task(bind=True, name="app.tasks.backtest_tasks.run_backtest", time_limit=3600)
def run_backtest(self, job_id: int) -> dict:
    return backtest_engine.run(job_id)
```

`run(job_id)` 内部：
1. 同步 session 读 `BacktestJob`
2. 加载 K 线
3. 实例化策略
4. 循环 `on_bar`
5. 落 `BacktestTrade` + 更新 `BacktestJob.result + status`

## 性能

- 10 年日 K 单股票 ~2500 bar，纯计算 < 1 秒
- 100 只股票组合 ~250s（瓶颈是 ArcticDB 批读）
- 千万级 tick 回测 → 必须 Cython / Numba / Rust 重写撮合循环（Phase 5+）

## 验证

回测引擎必须有充足单元测试：

```python
def test_match_buy_at_next_open():
    bars = [bar1, bar2]
    orders = [PendingOrder("long", "open", 100)]
    trades = match(orders, bars[1])
    assert trades[0].price == bars[1].open_price
```

## 禁止

- ❌ **未来函数**：用 `bar[i]` 的 close 作为同一根 bar 的成交价
- ❌ **前向偷看**：策略 `on_bar(bar[i])` 时访问了 `bar[i+1]`
- ❌ 撮合考虑成交量但不限制（A 股有涨跌停和最小成交单位 100 股）
- ❌ 把回测结果写 ArcticDB（写 PG `BacktestJob.result`）
- ❌ 一个 task 跑超过 1 小时不分片
