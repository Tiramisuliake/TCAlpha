"""选股器 screen 过滤单元测试（mock Redis 快照）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _fake_snapshot_json() -> str:
    df = pd.DataFrame([
        {"symbol": "sh600000", "code": "600000", "name": "浦发银行", "price": 10.0,
         "pct_chg": 1.0, "amount": 5e8, "turnover": 2.0, "market_cap": 3000e8, "pe": 5.0, "pb": 0.6},
        {"symbol": "sh600519", "code": "600519", "name": "贵州茅台", "price": 1500.0,
         "pct_chg": -1.0, "amount": 3e9, "turnover": 0.5, "market_cap": 20000e8, "pe": 30.0, "pb": 10.0},
        {"symbol": "sz000001", "code": "000001", "name": "ST平安", "price": 12.0,
         "pct_chg": 2.0, "amount": 2e8, "turnover": 3.0, "market_cap": 2000e8, "pe": 8.0, "pb": 0.9},
    ])
    return df.to_json(orient="records", force_ascii=False)


class _FakeRedis:
    def __init__(self, raw: str | None) -> None:
        self._raw = raw

    async def get(self, _key: str) -> str | None:
        return self._raw


async def test_screen_filters_pe_and_excludes_st(monkeypatch):
    """PE≤10 + 排除 ST：只剩浦发（茅台 PE 高、ST 被排）。"""
    from app.services import screener

    monkeypatch.setattr(screener, "get_redis", lambda: _FakeRedis(_fake_snapshot_json()))
    res = await screener.screen({"pe_max": 10, "exclude_st": True})

    assert res["ready"] is True
    codes = {c["code"] for c in res["candidates"]}
    assert "600000" in codes        # PE 5 ≤ 10
    assert "600519" not in codes    # PE 30 > 10
    assert "000001" not in codes    # ST 排除


async def test_screen_amount_min_filter(monkeypatch):
    """成交额 ≥ 25 亿：只剩茅台（30亿）。"""
    from app.services import screener

    monkeypatch.setattr(screener, "get_redis", lambda: _FakeRedis(_fake_snapshot_json()))
    res = await screener.screen({"amount_min": 25})  # 25 亿
    codes = {c["code"] for c in res["candidates"]}
    assert codes == {"600519"}


async def test_screen_cache_miss_returns_not_ready(monkeypatch):
    """缓存为空 → ready False，触发后台刷新（mock delay 不真发 Celery）。"""
    from app.services import screener

    monkeypatch.setattr(screener, "get_redis", lambda: _FakeRedis(None))

    import app.tasks.data_tasks as dt

    class _FakeTask:
        @staticmethod
        def delay():
            return None

    monkeypatch.setattr(dt, "refresh_market_snapshot", _FakeTask)
    res = await screener.screen({})

    assert res["ready"] is False
    assert res["candidates"] == []


async def test_screen_factor_mode_scores_and_sorts(monkeypatch):
    """多因子模式：candidates 带 score 且按 score 降序。"""
    from app.services import screener

    monkeypatch.setattr(screener, "get_redis", lambda: _FakeRedis(_fake_snapshot_json()))
    res = await screener.screen(
        {"factor_mode": True, "w_momentum": 1, "w_value": 1, "w_turnover": 1}
    )

    assert res["ready"] is True
    cands = res["candidates"]
    assert len(cands) == 3
    assert all("score" in c for c in cands)
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)


# ── 短线技术选股（v0.8.9）────────────────────────────────────────────────


def _mk_kline(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    vols: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="Asia/Shanghai")
    close = np.array(closes, dtype=float)
    open_ = np.array(opens, dtype=float) if opens else close
    high = np.array(highs, dtype=float) if highs else close * 1.005
    low = np.array(lows, dtype=float) if lows else close * 0.995
    vol = np.array(vols, dtype=float) if vols else np.full(n, 1e6)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol,
         "amount": close * vol},
        index=idx,
    )


def _flat() -> pd.DataFrame:
    """横盘窄幅：任何短线形态都不命中。"""
    return _mk_kline([10.0] * 60, highs=[10.05] * 60, lows=[9.95] * 60)


@pytest.fixture
def _no_names(monkeypatch):
    """隔离 PG：name map 返回空（不影响 exclude_st，名称非 ST）。"""
    from app.services import short_term

    monkeypatch.setattr(short_term, "_name_map", lambda syms: {})


def test_short_term_volume_breakout(fake_arctic, _no_names):
    """放量突破：横盘后单日突破前 20 日高 + 量比 3×→命中；横盘票不命中。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    lib.write("sh600001", _mk_kline(
        [10.0] * 59 + [11.0],
        highs=[10.05] * 59 + [11.05],
        vols=[1e6] * 59 + [3e6],
    ))
    lib.write("sz000099", _flat())

    res = scan_short_term({"pattern": "volume_breakout", "vol_ratio_min": 1.5})
    syms = {c["symbol"] for c in res["candidates"]}
    assert "sh600001" in syms
    assert "sz000099" not in syms
    assert res["ready"] is True


def test_short_term_ma_long(fake_arctic, _no_names):
    """均线多头：持续上涨 MA5>MA10>MA20→命中；横盘票不命中。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    lib.write("sh600002", _mk_kline([9 + i * 0.05 for i in range(60)]))
    lib.write("sz000099", _flat())

    res = scan_short_term({"pattern": "ma_long"})
    syms = {c["symbol"] for c in res["candidates"]}
    assert "sh600002" in syms
    assert "sz000099" not in syms


def test_short_term_pullback(fake_arctic, _no_names):
    """回踩企稳：上升趋势中今日最低触及 MA10 收回→命中；横盘票不命中。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    closes = [9 + i * 0.05 for i in range(59)] + [11.95]
    lows = [c * 0.995 for c in closes[:-1]] + [10.0]  # 末根深探至 MA10 下方再收回
    lib.write("sh600003", _mk_kline(closes, lows=lows))
    lib.write("sz000099", _flat())

    res = scan_short_term({"pattern": "pullback"})
    syms = {c["symbol"] for c in res["candidates"]}
    assert "sh600003" in syms
    assert "sz000099" not in syms


def test_short_term_empty_lib_not_ready(fake_arctic, _no_names):
    """无历史 K 线 → ready False（提示先下载数据）。"""
    from app.services.short_term import scan_short_term

    res = scan_short_term({"pattern": "volume_breakout"})
    assert res["ready"] is False
    assert res["candidates"] == []


def test_short_term_scores_sorted(fake_arctic, _no_names):
    """多只命中 → candidates 带 score 且降序。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    # 两只放量突破，量比不同 → 动能打分有别
    lib.write("sh600001", _mk_kline([10.0] * 59 + [11.0], highs=[10.05] * 59 + [11.05], vols=[1e6] * 59 + [3e6]))
    lib.write("sh600004", _mk_kline([10.0] * 59 + [10.5], highs=[10.05] * 59 + [10.55], vols=[1e6] * 59 + [2e6]))

    res = scan_short_term({"pattern": "volume_breakout"})
    cands = res["candidates"]
    assert len(cands) == 2
    assert all("score" in c for c in cands)
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)


def test_short_term_unknown_pattern_raises(fake_arctic, _no_names):
    from app.services.short_term import scan_short_term

    with pytest.raises(ValueError, match="unknown pattern"):
        scan_short_term({"pattern": "foobar"})


def _kline_with_tail_limit_ups(boards: int, *, base: float = 10.0) -> pd.DataFrame:
    """构造尾部 N 连板的主板（10%）日 K：前 40 根横盘，末 N 根逐日精确涨停。"""
    closes = [base] * 40
    last = base
    for _ in range(boards):
        last = round(last * 1.1, 2)  # 主板涨停：昨收 ×1.1 两位小数
        closes.append(last)
    # high=close（一字/收于涨停），low 略低，volume 恒定
    return _mk_kline(closes, highs=closes, lows=[c * 0.97 for c in closes])


def test_short_term_limit_up_counts_boards(fake_arctic, _no_names):
    """涨停打板：三连板 / 一板 / 普通票 → limit_up 命中两只，boards 计数正确且按高度排序。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    lib.write("sh600001", _kline_with_tail_limit_ups(3))   # 三连板
    lib.write("sh600002", _kline_with_tail_limit_ups(1))   # 一板
    lib.write("sz000099", _flat())                          # 普通横盘

    res = scan_short_term({"pattern": "limit_up", "min_boards": 1})
    rows = {c["symbol"]: c for c in res["candidates"]}
    assert set(rows) == {"sh600001", "sh600002"}           # 横盘不命中
    assert rows["sh600001"]["boards"] == 3
    assert rows["sh600002"]["boards"] == 1
    # 连板高度优先排序
    assert res["candidates"][0]["symbol"] == "sh600001"


def test_short_term_min_boards_filter(fake_arctic, _no_names):
    """min_boards=2：仅连板数 ≥ 2 入选（一板被过滤）。"""
    from app.db.arctic import get_library
    from app.services.short_term import scan_short_term

    lib = get_library("bar_1d")
    lib.write("sh600001", _kline_with_tail_limit_ups(3))
    lib.write("sh600002", _kline_with_tail_limit_ups(1))

    res = scan_short_term({"pattern": "limit_up", "min_boards": 2})
    syms = {c["symbol"] for c in res["candidates"]}
    assert syms == {"sh600001"}


def test_board_limit_pct_by_board():
    """板块涨跌停比例：主板 10% / 创业板·科创板 20% / 北交所 30%。"""
    from app.services.short_term import _board_limit_pct

    assert _board_limit_pct("sh600000") == 0.10
    assert _board_limit_pct("sz300001") == 0.20
    assert _board_limit_pct("sh688001") == 0.20
    assert _board_limit_pct("bj830799") == 0.30


# ── 涨停次日溢价统计（打板复盘，v0.8.12）─────────────────────────────────


def test_limit_up_premium_single_stock(fake_arctic):
    """单只票一个涨停日：次日开盘/收盘/最高溢价与红盘率精确匹配。"""
    from app.db.arctic import get_library
    from app.services.short_term import limit_up_premium

    # 40 横盘 10 → 第41根涨停到 11.0 → 次日 open=11.5 close=11.3 high=12.0 → 之后平
    closes = [10.0] * 40 + [11.0] + [11.3, 11.3, 11.3]
    opens = [10.0] * 40 + [10.5] + [11.5, 11.3, 11.3]   # 次日（idx41）开盘 11.5
    highs = [10.05] * 40 + [11.0] + [12.0, 11.4, 11.4]
    get_library("bar_1d").write("sh600001", _mk_kline(closes, opens=opens, highs=highs))

    res = limit_up_premium(symbol="sh600001", lookback=250)

    assert res["ready"] is True
    assert res["count"] == 1
    assert res["avg_open_premium"] == pytest.approx(11.5 / 11.0 - 1, abs=1e-4)
    assert res["avg_close_premium"] == pytest.approx(11.3 / 11.0 - 1, abs=1e-4)
    assert res["avg_high_premium"] == pytest.approx(12.0 / 11.0 - 1, abs=1e-4)
    assert res["next_day_win_rate"] == 1.0  # 次日收盘 11.3 > 11.0
    assert res["by_boards"][0]["boards"] == "1板"


def test_limit_up_premium_no_limit_up(fake_arctic):
    """横盘无涨停 → count 0，各项归零。"""
    from app.db.arctic import get_library
    from app.services.short_term import limit_up_premium

    get_library("bar_1d").write("sz000099", _flat())
    res = limit_up_premium(symbol="sz000099")
    assert res["ready"] is True and res["count"] == 0
    assert res["by_boards"] == []


def test_limit_up_premium_empty_lib(fake_arctic):
    """空库 → ready False。"""
    from app.services.short_term import limit_up_premium

    assert limit_up_premium()["ready"] is False


def test_limit_up_premium_groups_by_boards(fake_arctic):
    """两连板产生 1板 + 2板两个涨停日样本，分组统计各 1 条。"""
    from app.db.arctic import get_library
    from app.services.short_term import limit_up_premium

    # 40 横盘 → 两连板（11.0, 12.10）→ 后续有次日数据
    closes = [10.0] * 40 + [11.0, 12.1] + [12.0, 12.0]
    get_library("bar_1d").write("sh600002", _mk_kline(closes, highs=closes))

    res = limit_up_premium(symbol="sh600002", lookback=250)
    labels = {g["boards"]: g for g in res["by_boards"]}
    assert "1板" in labels and "2板" in labels
    assert labels["1板"]["count"] == 1
    assert labels["2板"]["count"] == 1
    assert res["count"] == 2
    # 晋级率：1板日次日续板（晋级2板）→ 1.0；2板日次日未续板 → 0.0
    assert labels["1板"]["promote_rate"] == 1.0
    assert labels["2板"]["promote_rate"] == 0.0
