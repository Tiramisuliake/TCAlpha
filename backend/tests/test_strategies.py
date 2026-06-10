"""新增策略（RSI / MACD / 布林带）单元测试。"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest


def _trend_bars(make_bar, n: int = 160, amp: float = 5.0) -> list:
    """强波动正弦行情，确保趋势/均值回归策略能触发信号。"""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        make_bar(base + timedelta(days=i), open_=c - 0.1, high=c + 0.3, low=c - 0.3, close=c)
        for i, c in ((i, 10 + amp * math.sin(i / 6.0)) for i in range(n))
    ]


@pytest.mark.parametrize(
    "cls_name",
    [
        "MaCrossStrategy", "MacdStrategy", "RsiStrategy", "BollStrategy",
        "TurtleStrategy", "KdjStrategy", "GridStrategy", "DmiStrategy",
    ],
)
def test_strategy_registered(cls_name):
    from app.core.backtest_engine import get_strategy_class

    assert get_strategy_class(cls_name) is not None


def test_list_strategy_classes_exposes_minmax():
    """list_strategy_classes 含 4 策略且 params_schema 带 min/max。"""
    from app.core.backtest_engine import list_strategy_classes

    classes = {c["class_name"]: c for c in list_strategy_classes()}
    assert {"MaCrossStrategy", "MacdStrategy", "RsiStrategy", "BollStrategy"} <= set(classes)
    macd = classes["MacdStrategy"]["params_schema"]
    assert macd["fast"]["minimum"] == 2
    assert macd["fast"]["maximum"] == 100


@pytest.mark.parametrize(
    "cls_name,params",
    [
        ("MacdStrategy", {"fast": 12, "slow": 26, "signal": 9}),
        ("RsiStrategy", {"period": 14, "oversold": 30.0, "overbought": 70.0}),
        ("BollStrategy", {"period": 20, "dev": 2.0}),
        ("KdjStrategy", {"period": 9, "buy_below": 30.0, "sell_above": 70.0}),
        ("DmiStrategy", {"period": 14, "adx_threshold": 25.0}),
        ("GridStrategy", {"grid_pct": 0.05, "max_grids": 5}),
    ],
)
def test_strategy_on_bar_runs(make_bar, cls_name, params):
    """喂 160 根 bar 无异常，vars.direction 合法。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class(cls_name)("sh600000", params)
    for b in _trend_bars(make_bar):
        s.on_bar(b)
    assert s.vars.direction in (-1, 0, 1)


def test_macd_generates_buy_and_sell_signals(make_bar):
    """强波动下 MACD 金叉/死叉各至少触发一次（_pending_signal）。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("MacdStrategy")("sh600000", {"fast": 12, "slow": 26, "signal": 9})
    s.state.pos = 0
    opens = closes = 0
    for b in _trend_bars(make_bar):
        s.on_bar(b)
        sig = getattr(s, "_pending_signal", None)
        if sig:
            _, offset, vol = sig
            if offset == "open":
                opens += 1
                s.state.pos += vol
            else:
                closes += 1
                s.state.pos -= vol
    assert opens > 0
    assert closes > 0


def _drive(strategy, bars) -> tuple[int, int]:
    """逐 bar 驱动策略并模拟成交回写 pos，返回 (开仓次数, 平仓次数)。"""
    opens = closes = 0
    for b in bars:
        strategy.on_bar(b)
        sig = getattr(strategy, "_pending_signal", None)
        if sig:
            _, offset, vol = sig
            if offset == "open":
                opens += 1
                strategy.state.pos += vol
            else:
                closes += 1
                strategy.state.pos -= vol
    return opens, closes


def test_kdj_low_golden_cross_and_high_dead_cross(make_bar):
    """强波动正弦：KDJ 低位金叉至少开仓一次、高位死叉至少平仓一次。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("KdjStrategy")(
        "sh600000", {"period": 9, "buy_below": 30.0, "sell_above": 70.0}
    )
    opens, closes = _drive(s, _trend_bars(make_bar, n=200))
    assert opens > 0
    assert closes > 0


def test_kdj_values_in_range(make_bar):
    """K/D 递推值落在 [0, 100] 区间（J 可超界，不约束）。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("KdjStrategy")("sh600000", {"period": 9})
    for b in _trend_bars(make_bar, n=120):
        s.on_bar(b)
        s.state.pos = 0  # 不累计持仓，只验指标
    assert 0 <= s.state.k <= 100
    assert 0 <= s.state.d <= 100


def test_grid_buys_on_dip_and_sells_on_recovery(make_bar):
    """网格：锚定 10 元、5% 间距 → 跌至 8.9 买进 2 格，涨回 9.9 全部卖出。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("GridStrategy")("sh600000", {"grid_pct": 0.05, "max_grids": 5})
    base = datetime(2024, 1, 1, tzinfo=UTC)
    #          锚定   跌1格  跌2格  持平   涨回1格  涨回锚
    prices = [10.0, 9.45, 8.90, 8.90, 9.45, 9.99]
    opens = closes = 0
    for i, c in enumerate(prices):
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c + 0.05, low=c - 0.05, close=c))
        sig = s._pending_signal
        if sig:
            _, offset, vol = sig
            if offset == "open":
                opens += 1
                s.state.pos += vol
            else:
                closes += 1
                s.state.pos -= vol
    assert opens == 2    # 9.45 / 8.90 各买一格
    assert closes == 2   # 9.45 / 9.99 各卖一格
    assert s.state.pos == 0


def test_grid_respects_max_grids(make_bar):
    """暴跌穿透所有网格：持仓格数不超过 max_grids。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("GridStrategy")("sh600000", {"grid_pct": 0.05, "max_grids": 3})
    base = datetime(2024, 1, 1, tzinfo=UTC)
    prices = [10.0] + [10.0 - 0.5 * i for i in range(1, 12)]  # 一路跌到 4.5
    for i, c in enumerate(prices):
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c + 0.05, low=max(c - 0.05, 0.1), close=c))
        sig = s._pending_signal
        if sig and sig[1] == "open":
            s.state.pos += sig[2]
    assert s.state.pos == 3 * 100  # 最多 3 格


def test_dmi_opens_in_trend_and_closes_on_reversal(make_bar):
    """DMI：平缓 → 强上涨（ADX 走高 +DI>-DI）开多 → 转跌（-DI 反超）平多。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("DmiStrategy")("sh600519", {"period": 14, "adx_threshold": 20.0})
    base = datetime(2024, 1, 1, tzinfo=UTC)
    opens = closes = 0
    for i in range(160):
        if i < 60:
            c = 100 + math.sin(i * 0.3)  # 平缓震荡
        elif i < 110:
            c = 100 + (i - 60) * 1.5     # 强上涨
        else:
            c = 175 - (i - 110) * 1.5    # 转跌
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c))
        sig = s._pending_signal
        if sig:
            if sig[1] == "open":
                opens += 1
                s.state.pos += sig[2]
            else:
                closes += 1
                s.state.pos -= sig[2]
    assert opens > 0
    assert closes > 0


def test_turtle_breakout_open_and_close(make_bar):
    """海龟：上涨突破前 N 日高开多、回落跌破前 M 日低平多。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("TurtleStrategy")(
        "sh600519", {"entry_window": 20, "exit_window": 10}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    opens = closes = 0
    for i in range(120):
        if i < 30:
            c = 100 + math.sin(i * 0.3)  # 平缓
        elif i < 70:
            c = 100 + (i - 30) * 1.5  # 突破上涨
        else:
            c = 160 - (i - 70) * 1.2  # 回落
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c))
        sig = getattr(s, "_pending_signal", None)
        if sig:
            if sig[1] == "open":
                opens += 1
                s.state.pos += sig[2]
            else:
                closes += 1
                s.state.pos -= sig[2]
    assert opens > 0   # 突破开多
    assert closes > 0  # 跌破平多
