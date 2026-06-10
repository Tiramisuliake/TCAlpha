"""回测引擎核心函数单元测试（B2）。

只测纯函数 `_match_orders / _settle / _metrics`，不跑整条 run()——
后者需要 PG job + ArcticDB + Celery，作集成测试代价大，B 阶段先保单元覆盖。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.backtest_engine import (
    PendingOrder,
    Trade,
    _benchmark_metrics,
    _drawdown_interval,
    _limit_pct,
    _match_orders,
    _metrics,
    _monthly_returns,
    _rolling_sharpe,
    _round_trips,
    _settle,
    _streaks,
    run_sweep,
)


def _mk_trade(pnl: float) -> Trade:
    """构造一个带盈亏的平仓 Trade（仅用于 streak 测试，其余字段占位）。"""
    return Trade(
        dt=datetime(2025, 1, 1, tzinfo=UTC), direction="long", offset="close",
        price=10.0, volume=100, commission=0.0, pnl=pnl,
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


# ── 基准对比（benchmark / Alpha-Beta）──────────────────────────────────


def test_metrics_without_benchmark_has_no_benchmark_fields():
    """不传 benchmark_close（默认）：结果不含任何基准字段，向后兼容。"""
    dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    equity = pd.Series([100.0, 101.0, 102.0, 103.0], index=dates)
    m = _metrics(equity, trades=[], init_capital=100.0)
    assert "benchmark" not in m
    assert "alpha" not in m and "beta" not in m


def test_benchmark_metrics_flat_benchmark():
    """基准完全走平：基准收益 0，超额 = 策略总收益，beta = 0；曲线对齐且字段齐全。

    equity 用 UTC、benchmark 用 Asia/Shanghai，验证跨时区按自然日对齐不错位。
    """
    eq_dates = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
    equity = pd.Series([100.0, 102.0, 104.0, 103.0, 110.0], index=eq_dates)

    bench_dates = pd.date_range("2025-01-01", periods=5, freq="D", tz="Asia/Shanghai")
    benchmark = pd.Series([3000.0] * 5, index=bench_dates)  # 完全走平

    b = _benchmark_metrics(equity, benchmark, init_capital=100.0, benchmark_name="沪深300")

    assert b["benchmark"] == "沪深300"
    assert b["benchmark_return"] == pytest.approx(0.0, abs=1e-9)
    assert b["excess_return"] == pytest.approx(0.10, rel=1e-3)  # 策略总收益 10%
    assert b["beta"] == 0.0  # 基准方差为 0 → beta 取 0
    assert len(b["benchmark_curve"]) == 5
    # 归一化基准曲线起点 = 策略起始资金
    assert b["benchmark_curve"][0]["value"] == pytest.approx(100.0)


def test_benchmark_metrics_correlated_positive_beta():
    """基准与策略同向波动 → beta > 0，且含信息比率字段。"""
    eq_dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100, 102, 101, 105, 104, 108], index=eq_dates, dtype=float)
    bench_dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="Asia/Shanghai")
    benchmark = pd.Series([3000, 3060, 3030, 3150, 3120, 3240], index=bench_dates, dtype=float)

    b = _benchmark_metrics(equity, benchmark, init_capital=100.0)
    assert b["beta"] > 0
    assert "information_ratio" in b


def test_metrics_with_benchmark_merges_fields():
    """_metrics 传 benchmark_close：结果合并基准字段。"""
    eq_dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    equity = pd.Series([100.0, 101.0, 102.0, 103.0], index=eq_dates)
    bench_dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="Asia/Shanghai")
    benchmark = pd.Series([3000.0, 3010.0, 3005.0, 3020.0], index=bench_dates)

    m = _metrics(equity, trades=[], init_capital=100.0, benchmark_close=benchmark)
    assert "benchmark" in m and "alpha" in m and "beta" in m
    assert "benchmark_curve" in m and len(m["benchmark_curve"]) == 4


# ── run() 端到端（S3：跨 session 访问 detached 对象回归）──────────────────


def test_run_end_to_end_persists_done(sync_db, sample_bars_arctic, monkeypatch):
    """整条 run() 跑通并落库 done。

    回归：修复前 run() 在第一个 session commit 后（job 已 detach）继续访问
    job.symbol / job.params 等，会抛 DetachedInstanceError。
    """
    from datetime import date

    from app.core.backtest_engine import run
    from app.db.models.backtest import BacktestJob

    # 基准下载在测试环境不联网：stub 成空 Series（基准跳过，不影响主回测落库）
    monkeypatch.setattr(
        "app.core.backtest_engine._load_index_close",
        lambda *a, **k: pd.Series(dtype=float),
    )

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


# ── 涨跌停 / 停牌撮合约束（④）──────────────────────────────────────────


def test_limit_pct_by_board():
    """板块涨跌停比例：主板 10% / 创业板·科创板 20% / 北交所 30%。"""
    assert _limit_pct("sh600000") == 0.10
    assert _limit_pct("sz000001") == 0.10
    assert _limit_pct("sz300001") == 0.20
    assert _limit_pct("sh688001") == 0.20
    assert _limit_pct("bj830799") == 0.30


def test_match_orders_suspension_no_fill(make_bar):
    """停牌（volume==0）：挂单不成交。"""
    bar = make_bar(datetime(2025, 1, 2), open_=10, high=10, low=10, close=10, volume=0)
    trades, pos = _match_orders(
        [PendingOrder("long", "open", 100)], bar, 0.0003, 0.01, 0, prev_close=10, symbol="sh600000"
    )
    assert trades == [] and pos == 0


def test_match_orders_limit_up_blocks_buy(make_bar):
    """一字涨停（主板 prev=10 → 涨停 11）：买不进。"""
    bar = make_bar(datetime(2025, 1, 2), open_=11, high=11, low=11, close=11)
    trades, pos = _match_orders(
        [PendingOrder("long", "open", 100)], bar, 0.0003, 0.01, 0, prev_close=10, symbol="sh600000"
    )
    assert trades == [] and pos == 0


def test_match_orders_limit_down_blocks_sell(make_bar):
    """一字跌停（主板 prev=10 → 跌停 9）：卖不出，持仓不变。"""
    bar = make_bar(datetime(2025, 1, 2), open_=9, high=9, low=9, close=9)
    trades, pos = _match_orders(
        [PendingOrder("long", "close", 100)], bar, 0.0003, 0.01, 100, prev_close=10, symbol="sh600000"
    )
    assert trades == [] and pos == 100


def test_match_orders_no_limit_when_prev_close_none(make_bar):
    """prev_close=None：不做涨跌停约束（向后兼容），一字涨停也成交。"""
    bar = make_bar(datetime(2025, 1, 2), open_=11, high=11, low=11, close=11)
    trades, pos = _match_orders([PendingOrder("long", "open", 100)], bar, 0.0003, 0.01, 0)
    assert len(trades) == 1 and pos == 100


# ── run_sweep 网格扫参 ─────────────────────────────────────────────────


def test_run_sweep_grid(fake_arctic, sample_bars_arctic):
    """笛卡尔积扫参：2×2=4 组合，按 target 排序返回 best。"""
    res = run_sweep(
        "sh600000", "MaCrossStrategy",
        {"fast": [5, 10], "slow": [20, 30]},
        "2025-01-01", "2026-01-01",
        1_000_000.0, 0.0003, 0.01, "sharpe",
    )
    assert res["count"] == 4
    assert len(res["results"]) == 4
    assert res["param_keys"] == ["fast", "slow"]
    assert res["best"] is not None
    assert "sharpe" in res["best"]["metrics"]


# ── 绩效深化：风险标量 / 回撤区间 / 连胜连亏 / 月度 / 滚动 ────────────────


def test_metrics_includes_deepened_fields():
    """_metrics 输出含全部深化字段（向后兼容地追加）。"""
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100.0, 102.0, 105.0, 103.0, 108.0, 110.0], index=dates)
    m = _metrics(equity, trades=[], init_capital=100.0)
    for k in (
        "calmar", "volatility", "avg_win", "avg_loss",
        "max_win_streak", "max_lose_streak",
        "max_dd_start", "max_dd_end", "max_dd_recovery", "max_dd_days",
        "monthly_returns", "rolling_sharpe",
    ):
        assert k in m, f"missing deepened field: {k}"


def test_drawdown_interval_peak_trough_recovery():
    """峰 100(d0) → 谷 90(d2) → 修复回 100(d4)：起止/修复/天数都对。"""
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100, 95, 90, 95, 100, 101], index=dates, dtype=float)
    d = _drawdown_interval(equity)
    assert d["max_dd_start"] == "2025-01-01"
    assert d["max_dd_end"] == "2025-01-03"
    assert d["max_dd_recovery"] == "2025-01-05"
    assert d["max_dd_days"] == 2


def test_drawdown_interval_no_drawdown():
    """单调上涨 → 无回撤，四项全退化。"""
    dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    equity = pd.Series([100, 101, 102, 103], index=dates, dtype=float)
    d = _drawdown_interval(equity)
    assert d == {
        "max_dd_start": None, "max_dd_end": None,
        "max_dd_recovery": None, "max_dd_days": 0,
    }


def test_drawdown_interval_still_underwater():
    """截止结束仍未回到前高 → recovery 为 None。"""
    dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    equity = pd.Series([100, 90, 85, 88], index=dates, dtype=float)
    d = _drawdown_interval(equity)
    assert d["max_dd_start"] == "2025-01-01"
    assert d["max_dd_end"] == "2025-01-03"
    assert d["max_dd_recovery"] is None


def test_streaks_win_and_lose():
    """连胜 2、连亏 3。"""
    trades = [_mk_trade(p) for p in (10, 5, -3, -2, -1, 4)]
    max_win, max_lose = _streaks(trades)
    assert max_win == 2
    assert max_lose == 3


def test_monthly_returns_spans_three_months():
    """跨 1-3 月、资金递增 → 3 个月度收益且均为正，首月以 init 为基。"""
    dates = pd.date_range("2025-01-01", "2025-03-31", freq="D", tz="UTC")
    equity = pd.Series(np.arange(100, 100 + len(dates), dtype=float), index=dates)
    mr = _monthly_returns(equity, init_capital=100.0)
    assert len(mr) == 3
    assert mr[0]["month"] == "2025-01"
    assert all(p["value"] > 0 for p in mr)


def test_rolling_sharpe_window():
    """短于窗口 → 空；长于窗口 → 长度 = N - window + 1。"""
    short = pd.Series([0.01, 0.02], index=pd.date_range("2025-01-01", periods=2, tz="UTC"))
    assert _rolling_sharpe(short, window=60) == []

    dates = pd.date_range("2025-01-01", periods=80, freq="D", tz="UTC")
    rets = pd.Series(np.tile([0.01, -0.005], 40), index=dates)  # 交替→滚动 std 恒非零
    rs = _rolling_sharpe(rets, window=60)
    assert len(rs) == 80 - 60 + 1
    assert all("dt" in p and "value" in p for p in rs)


def test_calmar_positive_for_profitable_with_drawdown():
    """有回撤的盈利曲线 → Calmar > 0。"""
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100, 102, 105, 103, 108, 110], index=dates, dtype=float)
    m = _metrics(equity, trades=[], init_capital=100.0)
    assert m["max_drawdown"] < 0
    assert m["calmar"] > 0


# ── 基准深化：滚动 Beta + 相对强弱 ─────────────────────────────────────


def test_benchmark_relative_strength_outperform_flat():
    """基准走平、策略上涨 → 相对强弱末值 > 1；样本不足 60 → 滚动 Beta 为空。"""
    eq_dates = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
    equity = pd.Series([100.0, 102.0, 104.0, 103.0, 110.0], index=eq_dates)
    bench_dates = pd.date_range("2025-01-01", periods=5, freq="D", tz="Asia/Shanghai")
    benchmark = pd.Series([3000.0] * 5, index=bench_dates)

    b = _benchmark_metrics(equity, benchmark, init_capital=100.0, benchmark_name="沪深300")
    assert b["rolling_beta"] == []  # < 60 个交易日
    assert len(b["relative_strength"]) == 5
    assert b["relative_strength"][-1]["value"] > 1.0


# ── 交易明细深化（v0.8.3）：回合配对 / MAE/MFE / 期望 ─────────────────────


def _open_t(dt: datetime, price: float, vol: int) -> Trade:
    return Trade(dt=dt, direction="long", offset="open", price=price, volume=vol, commission=0.0)


def _close_t(dt: datetime, price: float, vol: int, pnl: float) -> Trade:
    return Trade(dt=dt, direction="long", offset="close", price=price, volume=vol, commission=0.0, pnl=pnl)


def test_round_trips_single_cycle():
    """单回合：开多 @10 → 3 天后平 @12，entry/exit/天数/收益率全对。"""
    d0 = datetime(2025, 1, 1, tzinfo=UTC)
    d3 = datetime(2025, 1, 4, tzinfo=UTC)
    trades = [_open_t(d0, 10.0, 100), _close_t(d3, 12.0, 100, pnl=200.0)]

    rts = _round_trips(trades)

    assert len(rts) == 1
    rt = rts[0]
    assert rt["entry_dt"] == "2025-01-01"
    assert rt["exit_dt"] == "2025-01-04"
    assert rt["holding_days"] == 3
    assert rt["entry_price"] == pytest.approx(10.0)
    assert rt["exit_price"] == pytest.approx(12.0)
    assert rt["pnl"] == pytest.approx(200.0)
    assert rt["return_pct"] == pytest.approx(200.0 / (10.0 * 100), abs=1e-4)
    # 无 bars → MAE/MFE 缺省
    assert rt["mae"] is None and rt["mfe"] is None


def test_round_trips_partial_close_splits_two_trips():
    """开 200 股、分两批平 → 拆成 2 个回合，共享同一进场日。"""
    d0 = datetime(2025, 1, 1, tzinfo=UTC)
    d2 = datetime(2025, 1, 3, tzinfo=UTC)
    d4 = datetime(2025, 1, 5, tzinfo=UTC)
    trades = [
        _open_t(d0, 10.0, 200),
        _close_t(d2, 12.0, 100, pnl=200.0),
        _close_t(d4, 11.0, 100, pnl=100.0),
    ]

    rts = _round_trips(trades)

    assert len(rts) == 2
    assert rts[0]["entry_dt"] == rts[1]["entry_dt"] == "2025-01-01"
    assert rts[0]["holding_days"] == 2
    assert rts[1]["holding_days"] == 4
    assert rts[0]["volume"] == rts[1]["volume"] == 100


def test_round_trips_mae_mfe_from_bars(make_bar):
    """带 bars：持仓期间最低 9 / 最高 12，入场均价 10 → MAE=-10%、MFE=+20%。"""
    d = [datetime(2025, 1, 1 + i, tzinfo=UTC) for i in range(3)]
    bars = [
        make_bar(d[0], open_=10.0, high=10.5, low=9.8, close=10.2),
        make_bar(d[1], open_=10.2, high=12.0, low=9.0, close=11.0),
        make_bar(d[2], open_=11.0, high=11.5, low=10.8, close=11.2),
    ]
    trades = [_open_t(d[0], 10.0, 100), _close_t(d[2], 11.0, 100, pnl=100.0)]

    rts = _round_trips(trades, bars)

    assert len(rts) == 1
    assert rts[0]["mae"] == pytest.approx(9.0 / 10.0 - 1, abs=1e-4)   # -0.10
    assert rts[0]["mfe"] == pytest.approx(12.0 / 10.0 - 1, abs=1e-4)  # +0.20


def test_round_trips_orphan_close_skipped():
    """无持仓时出现 close（异常数据）→ 跳过不配对。"""
    d0 = datetime(2025, 1, 1, tzinfo=UTC)
    rts = _round_trips([_close_t(d0, 10.0, 100, pnl=0.0)])
    assert rts == []


def test_metrics_includes_trade_analysis_fields():
    """_metrics 追加交易级字段：round_trips / 持仓天数 / MAE/MFE / expectancy。"""
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100.0, 102.0, 105.0, 103.0, 108.0, 110.0], index=dates)
    trades = [
        _open_t(dates[0].to_pydatetime(), 10.0, 100),
        _close_t(dates[2].to_pydatetime(), 11.0, 100, pnl=100.0),
        _open_t(dates[3].to_pydatetime(), 11.0, 100),
        _close_t(dates[5].to_pydatetime(), 10.5, 100, pnl=-50.0),
    ]

    m = _metrics(equity, trades, init_capital=100.0)

    assert len(m["round_trips"]) == 2
    # 两回合各持仓 2 天
    assert m["avg_holding_days"] == pytest.approx(2.0)
    assert m["win_holding_days"] == pytest.approx(2.0)
    assert m["lose_holding_days"] == pytest.approx(2.0)
    # 期望 = 0.5×100 + 0.5×(-50) = 25
    assert m["expectancy"] == pytest.approx(25.0)
    # 未传 bars → MAE/MFE 退化为 None
    assert m["avg_mae"] is None and m["avg_mfe"] is None


def test_metrics_trade_analysis_backward_compat_no_trades():
    """无平仓交易：round_trips 空、持仓天数 0、expectancy 0，字段仍存在。"""
    dates = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    equity = pd.Series([100.0, 101.0, 102.0], index=dates)
    m = _metrics(equity, trades=[], init_capital=100.0)
    assert m["round_trips"] == []
    assert m["avg_holding_days"] == 0.0
    assert m["expectancy"] == 0.0
    assert m["avg_mae"] is None


def test_benchmark_rolling_beta_non_empty_long_series():
    """≥60 交易日、策略与基准相关 → 滚动 Beta 非空，相对强弱逐日对齐。"""
    n = 70
    eq_dates = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    bench_dates = pd.date_range("2025-01-01", periods=n, freq="D", tz="Asia/Shanghai")
    rng = np.random.RandomState(1)
    br = rng.normal(0.0005, 0.01, n)
    noise = rng.normal(0.0, 0.005, n)
    bench_prices = 3000.0 * np.cumprod(1 + br)
    eq_prices = 100.0 * np.cumprod(1 + (0.8 * br + noise))
    equity = pd.Series(eq_prices, index=eq_dates)
    benchmark = pd.Series(bench_prices, index=bench_dates)

    b = _benchmark_metrics(equity, benchmark, init_capital=100.0)
    assert len(b["rolling_beta"]) > 0
    assert len(b["relative_strength"]) == n
