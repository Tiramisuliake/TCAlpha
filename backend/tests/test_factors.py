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
