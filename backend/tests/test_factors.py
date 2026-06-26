"""时序多因子选股引擎单元测试（fake_arctic 注入历史日 K）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _kline(closes: list[float], *, vols: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="Asia/Shanghai")
    close = np.array(closes, dtype=float)
    vol = np.array(vols, dtype=float) if vols else np.full(n, 1e6)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": vol,
            "amount": close * vol,
        },
        index=idx,
    )


@pytest.fixture
def _no_names(monkeypatch):
    """隔离 PG：factors 模块的 _name_map 返回空（名称非 ST，不影响 exclude_st）。"""
    from app.services import factors

    monkeypatch.setattr(factors, "_name_map", lambda syms: {})


def _strong() -> pd.DataFrame:
    """持续上涨：高动量 + 正趋势斜率。"""
    return _kline([10 + i * 0.08 for i in range(70)])


def _flat() -> pd.DataFrame:
    """横盘：动量/趋势近零、波动最低。"""
    return _kline([10.0] * 70)


def _falling() -> pd.DataFrame:
    """持续下跌：负动量 + 负趋势斜率。"""
    return _kline([20 - i * 0.08 for i in range(70)])


def test_factor_screen_ranks_strong_first(fake_arctic, _no_names):
    """强势票综合分最高、下跌票最低；score 降序。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sz000002", _flat())
    lib.write("sh600003", _falling())

    res = factor_screen({})
    assert res["ready"] is True
    assert res["count"] == 3
    cands = res["candidates"]
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)
    assert cands[0]["symbol"] == "sh600001"   # 强势第一
    assert cands[-1]["symbol"] == "sh600003"  # 下跌垫底


def test_factor_screen_candidate_has_factor_fields(fake_arctic, _no_names):
    """候选暴露各因子原始值 + z 分 + 综合分 + 基础字段。"""
    from app.db.arctic import get_library
    from app.services.factors import FACTORS, factor_screen

    get_library("bar_1d").write("sh600001", _strong())
    c = factor_screen({})["candidates"][0]
    for f in FACTORS:
        assert f in c            # 原始因子值
        assert f"{f}_z" in c     # 截面 z 分
    assert {"symbol", "code", "name", "price", "score"} <= set(c)
    # 强势票动量为正
    assert c["mom_20"] > 0 and c["mom_60"] > 0


def test_factor_screen_zero_weights_zero_score(fake_arctic, _no_names):
    """所有权重置 0 → 综合分全 0（仍 ready，仅不参与加权）。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sz000002", _flat())

    weights = {f: 0 for f in ("mom_20", "mom_60", "volatility", "trend_slope", "vol_surge")}
    res = factor_screen({"weights": weights})
    assert res["ready"] is True and res["count"] == 2
    assert all(c["score"] == 0 for c in res["candidates"])


def test_factor_screen_single_weight_drives_order(fake_arctic, _no_names):
    """仅留 mom_20 权重 → 排序由 20 日动量决定（强势 > 横盘）。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sz000002", _flat())

    weights = {"mom_20": 1, "mom_60": 0, "volatility": 0, "trend_slope": 0, "vol_surge": 0}
    cands = factor_screen({"weights": weights})["candidates"]
    assert cands[0]["symbol"] == "sh600001"


def test_factor_screen_price_filter(fake_arctic, _no_names):
    """price_min 过滤掉低价横盘票。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())   # 末价 ≈ 15.5
    lib.write("sz000002", _flat())     # 末价 10

    syms = {c["symbol"] for c in factor_screen({"price_min": 12})["candidates"]}
    assert syms == {"sh600001"}


def test_factor_screen_empty_lib_not_ready(fake_arctic, _no_names):
    """空库 → ready False（提示先下载数据）。"""
    from app.services.factors import factor_screen

    res = factor_screen({})
    assert res["ready"] is False
    assert res["candidates"] == []


# ── 反转风格因子（v0.8.26）───────────────────────────────────────────────


def test_factor_reversal_fields_present(fake_arctic, _no_names):
    """候选暴露反转因子原始值 + z 分；强势票 RSI 偏高（超买）。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    get_library("bar_1d").write("sh600001", _strong())
    c = factor_screen({})["candidates"][0]
    for f in ("rev_5", "rsi_14", "boll_pctb"):
        assert f in c and f"{f}_z" in c
    assert c["rsi_14"] > 50          # 持续上涨 → 超买
    assert 0.0 <= c["rsi_14"] <= 100.0


def test_factor_reversal_weights_pick_oversold(fake_arctic, _no_names):
    """开启反转权重、关闭动量 → 超卖下跌票综合分高于强势超买票。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())    # 持续上涨：超买
    lib.write("sh600003", _falling())   # 持续下跌：超卖

    weights = {
        "mom_20": 0, "mom_60": 0, "volatility": 0, "trend_slope": 0, "vol_surge": 0,
        "rev_5": 1, "rsi_14": 1, "boll_pctb": 1,
    }
    cands = factor_screen({"weights": weights})["candidates"]
    assert cands[0]["symbol"] == "sh600003"               # 超卖票反转得分高
    assert cands[0]["rsi_14"] < cands[-1]["rsi_14"]       # 超卖 RSI 更低


def test_factor_default_weights_ignore_reversal(fake_arctic, _no_names):
    """缺省权重下反转因子权重 0：动量主导，强势票仍排第一。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sh600003", _falling())

    cands = factor_screen({})["candidates"]
    assert cands[0]["symbol"] == "sh600001"


# ── 量价 / 资金行为因子（v0.8.27）─────────────────────────────────────────


def test_factor_pricevolume_fields_present(fake_arctic, _no_names):
    """候选暴露量价因子原始值 + z 分；持续上涨票 OBV 斜率为正、流动性优于下跌票。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sh600003", _falling())

    rows = {c["symbol"]: c for c in factor_screen({})["candidates"]}
    up = rows["sh600001"]
    for f in ("corr_pv", "amihud", "obv_slope"):
        assert f in up and f"{f}_z" in up
    assert up["obv_slope"] > 0                              # 持续上涨：OBV 净流入
    assert rows["sh600003"]["obv_slope"] < 0               # 持续下跌：OBV 净流出
    assert up["amihud"] >= 0                                # Amihud 非流动性恒非负


def test_factor_obv_weight_picks_inflow(fake_arctic, _no_names):
    """仅开 OBV 斜率权重、关其余 → 资金净流入票（上涨）排第一。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sh600003", _falling())

    weights = {
        "mom_20": 0, "mom_60": 0, "volatility": 0, "trend_slope": 0, "vol_surge": 0,
        "rev_5": 0, "rsi_14": 0, "boll_pctb": 0, "obv_slope": 1,
    }
    cands = factor_screen({"weights": weights})["candidates"]
    assert cands[0]["symbol"] == "sh600001"


def test_factor_default_weights_ignore_pricevolume(fake_arctic, _no_names):
    """缺省权重下量价因子权重 0：动量主导，强势票仍排第一。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_screen

    lib = get_library("bar_1d")
    lib.write("sh600001", _strong())
    lib.write("sh600003", _falling())

    assert factor_screen({})["candidates"][0]["symbol"] == "sh600001"


# ── 单因子有效性检验 IC + 分层（v0.8.28）─────────────────────────────────


def test_factor_ic_momentum_positive(fake_arctic):
    """8 票不同斜率指数趋势：动量与未来收益完全单调 → IC 强正、分层 Q5>Q1、多空 > 0。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_ic

    lib = get_library("bar_1d")
    for i in range(8):
        slope = (i - 3.5) * 0.012  # -0.042 .. +0.042，斜率单调
        closes = [10.0 * (1 + slope) ** k for k in range(160)]
        lib.write(f"sh60000{i}", _kline(closes))

    res = factor_ic("mom_20", hold_days=5, lookback=60, sample_points=4, max_scan=50)
    assert res["ready"] is True
    assert res["sample_count"] >= 1
    assert res["mean_ic"] > 0.5          # 单调 → 强正 rank IC
    assert res["long_short"] > 0         # 高动量档未来收益更高
    q = {x["q"]: x["avg_return"] for x in res["quantiles"]}
    assert q[5] > q[1]                    # 分层单调


def test_factor_ic_empty_lib(fake_arctic):
    """空库 → ready False。"""
    from app.services.factors import factor_ic

    assert factor_ic("mom_20")["ready"] is False


def test_factor_ic_unknown_factor(fake_arctic):
    from app.services.factors import factor_ic

    with pytest.raises(ValueError, match="unknown factor"):
        factor_ic("foobar")


def test_factor_ic_all_covers_factors(fake_arctic):
    """全因子横评：返回覆盖所有 FACTORS（带中文名），mom_20 IC 正。"""
    from app.db.arctic import get_library
    from app.services.factors import FACTORS, factor_ic_all

    lib = get_library("bar_1d")
    for i in range(8):
        slope = (i - 3.5) * 0.012
        closes = [10.0 * (1 + slope) ** k for k in range(160)]
        lib.write(f"sh60000{i}", _kline(closes))

    rows = factor_ic_all(hold_days=5, lookback=60, sample_points=4, max_scan=50)
    assert [r["factor"] for r in rows] == list(FACTORS)
    assert all(r["name"] for r in rows)          # 每行有中文名
    mom = next(r for r in rows if r["factor"] == "mom_20")
    assert mom["sample_count"] >= 1
    assert mom["mean_ic"] > 0.5                   # 单调动量 → 强正 IC
    assert mom["long_short"] > 0


def test_factor_ic_all_empty_lib(fake_arctic):
    """空库 → 仍返回每因子一行，sample_count 全 0。"""
    from app.services.factors import FACTORS, factor_ic_all

    rows = factor_ic_all()
    assert len(rows) == len(FACTORS)
    assert all(r["sample_count"] == 0 for r in rows)


# ── 多因子组合回测（v0.8.30）─────────────────────────────────────────────


def test_factor_portfolio_momentum_beats_bench(fake_arctic):
    """12 票分化趋势 + 默认权重（动量主导）：组合选中强势票，超额 > 0、净值增长。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_portfolio_backtest

    lib = get_library("bar_1d")
    for i in range(12):
        slope = (i - 5.5) * 0.01
        closes = [10.0 * (1 + slope) ** k for k in range(130)]
        lib.write(f"sh6000{i:02d}", _kline(closes))

    res = factor_portfolio_backtest(top_n=3, rebalance_days=5, lookback=40, max_scan=50)
    assert res["ready"] is True
    assert res["rebalance_count"] >= 1
    assert res["total_return"] > 0                 # 选中强势票 → 净值增长
    assert res["excess_return"] > 0                # 跑赢全市场等权基准
    assert len(res["equity_curve"]) == res["rebalance_count"]
    assert len(res["benchmark_curve"]) == res["rebalance_count"]


def test_factor_portfolio_empty_lib(fake_arctic):
    """空库 → ready False。"""
    from app.services.factors import factor_portfolio_backtest

    assert factor_portfolio_backtest()["ready"] is False


def test_factor_portfolio_insufficient_names(fake_arctic):
    """票数 < top_n → 无有效调仓，ready True 但 rebalance_count 0。"""
    from app.db.arctic import get_library
    from app.services.factors import factor_portfolio_backtest

    closes = [10.0 * 1.01**k for k in range(130)]
    get_library("bar_1d").write("sh600001", _kline(closes))
    res = factor_portfolio_backtest(top_n=10, rebalance_days=5, lookback=40)
    assert res["ready"] is True
    assert res["rebalance_count"] == 0
