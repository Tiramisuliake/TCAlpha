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
        "AtrStopStrategy", "MaVolStrategy", "PullbackStrategy", "BollSqueezeStrategy",
        "CciStrategy", "VwapBiasStrategy", "PyramidTurtleStrategy",
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
        ("AtrStopStrategy", {"entry_window": 20, "atr_period": 14, "atr_mult": 3.0}),
        ("MaVolStrategy", {"fast": 5, "slow": 20, "vol_window": 20, "vol_ratio": 1.5}),
        ("PullbackStrategy", {"trend_window": 30, "pull_window": 10}),
        ("BollSqueezeStrategy", {"period": 20, "dev": 2.0, "squeeze_th": 0.10}),
        ("CciStrategy", {"period": 20, "oversold": -100.0, "overbought": 100.0}),
        ("VwapBiasStrategy", {"period": 20, "bias_pct": 0.05}),
        ("PyramidTurtleStrategy", {"entry_window": 20, "exit_window": 10, "max_units": 4}),
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


def test_atr_stop_opens_on_breakout_closes_on_stop(make_bar):
    """ATR 吊灯：平缓 → 强上涨突破开多 → 急跌触发跟踪止损平多。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("AtrStopStrategy")(
        "sh600519", {"entry_window": 20, "atr_period": 14, "atr_mult": 3.0}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    opens = closes = 0
    for i in range(105):
        if i < 55:
            c = 100 + math.sin(i * 0.3)        # 平缓震荡
        elif i < 86:
            c = 100 + (i - 55) * 1.5           # 强上涨（突破入场，止损线随高点上移）
        else:
            c = 146.5 - (i - 86) * 3.0         # 急跌（跌破吊灯止损）
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c))
        sig = s._pending_signal
        if sig:
            if sig[1] == "open":
                opens += 1
                s.state.pos += sig[2]
            else:
                closes += 1
                s.state.pos -= sig[2]
    assert opens > 0   # 突破开多
    assert closes > 0  # 止损平多


def test_atr_stop_line_monotonic_while_holding(make_bar):
    """持仓期间吊灯止损线只升不降（锁浮盈）。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("AtrStopStrategy")(
        "sh600519", {"entry_window": 20, "atr_period": 14, "atr_mult": 3.0}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    stops: list[float] = []
    for i in range(90):
        c = 100 + math.sin(i * 0.3) if i < 55 else 100 + (i - 55) * 1.5
        s.on_bar(make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c))
        sig = s._pending_signal
        if sig and sig[1] == "open":
            s.state.pos += sig[2]
        if s.state.pos > 0:
            stops.append(s.state.stop_line)
    assert len(stops) > 5
    assert all(b >= a for a, b in zip(stops, stops[1:], strict=False))


def _ma_vol_prices() -> list[tuple[float, float]]:
    """(close, volume) 序列：缓跌(量平) → 放量上涨(金叉) → 缩量下跌(死叉)。"""
    path: list[tuple[float, float]] = []
    for i in range(55):
        path.append((100 - i * 0.1, 1_000_000))       # 缓跌，fast < slow
    for i in range(16):
        path.append((94.5 + (i + 1) * 1.0, 3_000_000))  # 放量上涨 → 放量金叉
    for i in range(20):
        path.append((110.5 - (i + 1) * 1.0, 1_000_000))  # 缩量回落 → 死叉
    return path


def test_ma_vol_opens_on_volume_confirmed_cross(make_bar):
    """放量金叉 → 开多；随后死叉 → 平多。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("MaVolStrategy")(
        "sh600000", {"fast": 5, "slow": 20, "vol_window": 20, "vol_ratio": 1.5}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c, volume=v)
        for i, (c, v) in enumerate(_ma_vol_prices())
    ]
    opens, closes = _drive(s, bars)
    assert opens > 0
    assert closes > 0


def test_ma_vol_skips_cross_without_volume(make_bar):
    """同样的价格路径但量能全程走平：金叉不放量 → 全程不开仓。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("MaVolStrategy")(
        "sh600000", {"fast": 5, "slow": 20, "vol_window": 20, "vol_ratio": 1.5}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c, volume=1_000_000)
        for i, (c, _) in enumerate(_ma_vol_prices())
    ]
    opens, _ = _drive(s, bars)
    assert opens == 0


def test_pullback_buys_dip_in_uptrend_sells_on_trend_break(make_bar):
    """趋势回踩：上行带回调的行情触发回踩买入，末段暴跌破趋势线平多。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("PullbackStrategy")(
        "sh600000", {"trend_window": 30, "pull_window": 10}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(200):
        c = 100 + 0.4 * i + 4 * math.sin(i / 6.0)  # 上行 + 周期性回调
        bars.append(make_bar(base + timedelta(days=i), open_=c, high=c + 0.5, low=c - 1.5, close=c))
    last = 100 + 0.4 * 199 + 4 * math.sin(199 / 6.0)
    for j in range(30):
        c = last - (j + 1) * 2.0  # 暴跌破趋势线
        bars.append(make_bar(base + timedelta(days=200 + j), open_=c, high=c + 0.5, low=c - 1.5, close=c))

    opens, closes = _drive(s, bars)
    assert opens > 0
    assert closes > 0


def test_pullback_never_buys_in_downtrend(make_bar):
    """趋势闸门：单边下跌（收盘恒在趋势线下方）→ 全程不开仓。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("PullbackStrategy")(
        "sh600000", {"trend_window": 30, "pull_window": 10}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        make_bar(base + timedelta(days=i), open_=c, high=c + 0.5, low=c - 1.5, close=c)
        for i, c in ((i, 200 - i * 0.8) for i in range(180))
    ]
    opens, _ = _drive(s, bars)
    assert opens == 0


def _squeeze_path(noise: float = 0.15) -> list[float]:
    """横盘 60 根（±noise 决定带宽）→ 向上突破 → 回落跌破中轨。"""
    closes = [100 + noise * ((-1) ** i) for i in range(60)]
    closes += [103.0, 104.0, 104.5]                          # 突破上轨
    closes += [104.0 - (j + 1) * 1.5 for j in range(6)]      # 回落跌破中轨
    return closes


def test_boll_squeeze_breakout_opens_then_mid_break_closes(make_bar):
    """收口后突破上轨开多一次，跌破中轨平多一次。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("BollSqueezeStrategy")(
        "sh600000", {"period": 20, "dev": 2.0, "squeeze_th": 0.10}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        make_bar(base + timedelta(days=i), open_=c, high=c + 0.1, low=c - 0.1, close=c)
        for i, c in enumerate(_squeeze_path())
    ]
    opens, closes = _drive(s, bars)
    assert opens == 1
    assert closes == 1


def test_boll_squeeze_gate_blocks_breakout_without_squeeze(make_bar):
    """挤压闸门：横盘噪声大（带宽 ~4% > 阈值 1%）→ 同样突破上轨也不开仓。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("BollSqueezeStrategy")(
        "sh600000", {"period": 20, "dev": 2.0, "squeeze_th": 0.01}
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        make_bar(base + timedelta(days=i), open_=c, high=c + 0.1, low=c - 0.1, close=c)
        for i, c in enumerate(_squeeze_path(noise=1.0))
    ]
    opens, _ = _drive(s, bars)
    assert opens == 0


def test_cci_cross_open_and_close(make_bar):
    """CCI：强波动正弦下，超卖上穿开多、超买下穿平多各至少触发一次。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("CciStrategy")(
        "sh600000", {"period": 20, "oversold": -100.0, "overbought": 100.0}
    )
    opens, closes = _drive(s, _trend_bars(make_bar, n=240, amp=6.0))
    assert opens > 0
    assert closes > 0


def test_vwap_bias_buys_on_undershoot_sells_on_recovery(make_bar):
    """VWAP 偏离：上行后急跌至 VWAP 下方 5% 买入，反弹回 VWAP 上方卖出。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("VwapBiasStrategy")("sh600000", {"period": 20, "bias_pct": 0.05})
    base = datetime(2024, 1, 1, tzinfo=UTC)
    prices = (
        [100.0] * 55                              # 横盘垫高 VWAP + 满足 ArrayManager 预热
        + [100 - i * 2.0 for i in range(1, 16)]   # 急跌至 70，穿破 VWAP×0.95
        + [70 + i * 3.0 for i in range(1, 21)]    # 强反弹回 VWAP 上方
    )
    opens, closes = _drive(
        s,
        [make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c)
         for i, c in enumerate(prices)],
    )
    assert opens > 0
    assert closes > 0


def test_pyramid_turtle_adds_up_to_max_then_full_close(make_bar):
    """金字塔：持续上涨加仓至 max_units 封顶，随后暴跌跌破下轨一次性全平归零。"""
    from app.core.backtest_engine import get_strategy_class

    s = get_strategy_class("PyramidTurtleStrategy")(
        "sh600519",
        {"entry_window": 20, "exit_window": 10, "atr_period": 14, "add_step": 0.5, "max_units": 4},
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    max_pos = 0
    bars = []
    for i in range(120):
        if i < 30:
            c = 100 + math.sin(i * 0.3)       # 平缓蓄势
        elif i < 95:
            c = 100 + (i - 30) * 2.0          # 持续强上涨 → 突破 + 多次加仓
        else:
            c = 230 - (i - 95) * 8.0          # 暴跌跌破下轨
        bars.append(make_bar(base + timedelta(days=i), open_=c, high=c * 1.01, low=c * 0.99, close=c))

    for b in bars:
        s.on_bar(b)
        sig = s._pending_signal
        if sig:
            _, offset, vol = sig
            s.state.pos += vol if offset == "open" else -vol
            max_pos = max(max_pos, s.state.pos)

    assert max_pos == 4 * 100   # 加仓封顶在 max_units
    assert s.state.pos == 0     # 跌破下轨后全平


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
