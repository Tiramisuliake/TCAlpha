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
    "cls_name", ["MaCrossStrategy", "MacdStrategy", "RsiStrategy", "BollStrategy", "TurtleStrategy"]
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
