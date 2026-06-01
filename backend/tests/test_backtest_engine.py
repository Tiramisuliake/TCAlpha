"""回测引擎核心函数单元测试（B2）。

只测纯函数 `_match_orders / _settle / _metrics`，不跑整条 run()——
后者需要 PG job + ArcticDB + Celery，作集成测试代价大，B 阶段先保单元覆盖。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.core.backtest_engine import (
    PendingOrder,
    Trade,
    _match_orders,
    _metrics,
    _settle,
)

# ── _match_orders ─────────────────────────────────────────────────────


def test_match_orders_long_open(make_bar):
    """开多头：next_bar 开盘价 + slippage，pos += volume。"""
    bar = make_bar(datetime(2025, 1, 2), open_=10.0)
    pending = [PendingOrder(direction="long", offset="open", volume=100)]

    trades, pos = _match_orders(pending, bar, 0.0003, 0.01, pos=0)

    assert len(trades) == 1
    t = trades[0]
    assert t.offset == "open"
    assert t.direction == "long"
    assert t.price == pytest.approx(10.01)  # 10.0 + slippage
    assert t.volume == 100
    assert t.commission == pytest.approx(10.01 * 100 * 0.0003)
    assert pos == 100


def test_match_orders_long_close_includes_stamp_duty(make_bar):
    """平多头：扣印花税 0.1%。"""
    bar = make_bar(datetime(2025, 1, 3), open_=11.0)
    pending = [PendingOrder(direction="long", offset="close", volume=100)]

    trades, pos = _match_orders(pending, bar, 0.0003, 0.01, pos=100)

    assert len(trades) == 1
    t = trades[0]
    exec_price = 11.0 - 0.01  # close long → 卖出，价格 - slippage
    expected_comm = exec_price * 100 * 0.0003 + exec_price * 100 * 0.001
    assert t.price == pytest.approx(exec_price)
    assert t.commission == pytest.approx(expected_comm)
    assert pos == 0


def test_match_orders_close_clamped_by_position(make_bar):
    """平仓量大于持仓时，按持仓量截断；持仓 = 0 时直接跳过。"""
    bar = make_bar(datetime(2025, 1, 4), open_=10.0)

    # 持仓 50，但下单平 200 → 实际只成交 50
    trades, pos = _match_orders(
        [PendingOrder("long", "close", 200)], bar, 0.0003, 0.0, pos=50
    )
    assert len(trades) == 1 and trades[0].volume == 50 and pos == 0

    # 持仓 0 时下平仓单 → 不成交
    trades, pos = _match_orders(
        [PendingOrder("long", "close", 100)], bar, 0.0003, 0.0, pos=0
    )
    assert trades == [] and pos == 0


# ── _settle ───────────────────────────────────────────────────────────


def _make_bars(make_bar, prices: list[float]) -> list:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return [
        make_bar(base + timedelta(days=i), open_=p, close=p, high=p * 1.01, low=p * 0.99)
        for i, p in enumerate(prices)
    ]


def test_settle_profitable_long_round_trip(make_bar):
    """开多 100 股 @10，平仓 @12，盈利约 200 - 手续费。"""
    bars = _make_bars(make_bar, [10, 11, 12])
    dt_open = bars[0].datetime
    dt_close = bars[2].datetime
    trades = [
        Trade(dt=dt_open, direction="long", offset="open",
              price=10.0, volume=100, commission=0.3),
        Trade(dt=dt_close, direction="long", offset="close",
              price=12.0, volume=100, commission=1.56),  # 0.0003 + 0.001
    ]

    equity = _settle(trades, bars, init_capital=10_000.0)

    assert len(equity) == 3
    # 最终 = 初始 + (12-10)*100 - 手续费
    assert equity.iloc[-1] == pytest.approx(10_000 + 200 - 0.3 - 1.56)
    # 中间持仓时按当日收盘价 mark-to-market
    assert equity.iloc[1] == pytest.approx(10_000 - 10*100 - 0.3 + 11*100)


def test_settle_empty_bars_returns_init_capital(make_bar):
    """空 bar 列表 → 单点曲线 = 初始资金。"""
    equity = _settle([], [], init_capital=50_000.0)
    assert len(equity) == 1
    assert equity.iloc[0] == 50_000.0


# ── _metrics ──────────────────────────────────────────────────────────


def test_metrics_basic_calculations():
    """简单上涨曲线：总收益、最大回撤、胜率都符合预期。"""
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100.0, 102.0, 105.0, 103.0, 108.0, 110.0], index=dates)
    trades = [
        Trade(dt=dates[1].to_pydatetime(), direction="long", offset="open",
              price=10.0, volume=100, commission=0.3),
        Trade(dt=dates[5].to_pydatetime(), direction="long", offset="close",
              price=11.0, volume=100, commission=0.4, pnl=50.0),
    ]

    m = _metrics(equity, trades, init_capital=100.0)

    assert m["total_return"] == pytest.approx(0.10, rel=1e-3)
    # cummax = [100,102,105,105,108,110] → drawdown 最深在 idx=3：(103-105)/105
    # _metrics 内部 round(4) 会丢精度，给个绝对容差
    assert m["max_drawdown"] == pytest.approx(-2 / 105, abs=1e-4)
    assert m["trade_count"] == 1
    assert m["win_rate"] == 1.0
    # 资金曲线导出
    assert len(m["equity_curve"]) == 6


def test_metrics_handles_no_closed_trades():
    """无平仓交易：胜率 0，盈亏比 inf 被替换为 9999。"""
    dates = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    equity = pd.Series([100.0, 100.0, 100.0], index=dates)
    m = _metrics(equity, trades=[], init_capital=100.0)

    assert m["trade_count"] == 0
    assert m["win_rate"] == 0.0
    assert m["profit_factor"] in (9999.0, 0.0)


# ── run() 端到端（S3：跨 session 访问 detached 对象回归）──────────────────


def test_run_end_to_end_persists_done(sync_db, sample_bars_arctic):
    """整条 run() 跑通并落库 done。

    回归：修复前 run() 在第一个 session commit 后（job 已 detach）继续访问
    job.symbol / job.params 等，会抛 DetachedInstanceError。
    """
    from datetime import date

    from app.core.backtest_engine import run
    from app.db.models.backtest import BacktestJob

    symbol = sample_bars_arctic  # "sh600000"
    with sync_db() as db:
        job = BacktestJob(
            user_id=1,
            name="it",
            class_name="MaCrossStrategy",
            symbol=symbol,
            params={"fast": 10, "slow": 20},
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            init_capital=1_000_000.0,
            commission_rate=0.0003,
            slippage=0.01,
            status="pending",
        )
        db.add(job)
        db.commit()
        job_id = job.id

    result = run(job_id)

    assert "equity_curve" in result and result["equity_curve"]
    assert result["final_equity"] > 0
    with sync_db() as db:
        job = db.get(BacktestJob, job_id)
        assert job.status == "done"
        assert job.result is not None
        assert job.finished_at is not None


# ── 策略实例隔离（S2：类属性单例污染回归）────────────────────────────────


def test_strategy_instances_have_isolated_state():
    """每个策略实例持有独立的 params/state/vars，互不污染，也不改类模板。

    回归：修复前 state/vars/params 是类属性单例，多实例共享同一对象。
    """
    from app.strategies.examples.ma_cross import MaCrossStrategy

    s1 = MaCrossStrategy("sh600000", {"fast": 5, "slow": 10})
    s2 = MaCrossStrategy("sz000001", {"fast": 20, "slow": 60})

    s1.state.pos = 100
    s1.state.fast_ma = 9.9
    s1.vars.direction = 1

    # s2 不受 s1 影响
    assert s2.state.pos == 0
    assert s2.state.fast_ma == 0.0
    assert s2.vars.direction == 0
    # 参数各自独立
    assert s1.params.fast == 5
    assert s2.params.fast == 20
    # 类属性模板未被实例操作污染
    assert MaCrossStrategy.state.pos == 0
    assert MaCrossStrategy.params.fast == 10
