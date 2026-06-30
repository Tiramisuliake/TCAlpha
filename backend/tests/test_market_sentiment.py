"""市场情绪温度计（services/market_sentiment.py）单元测试。"""
from __future__ import annotations

import pandas as pd


def _spot(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_compute_sentiment_counts_and_limits():
    """涨跌家数 / 涨跌停（按板块线）/ 温度计算正确。"""
    from app.services.market_sentiment import compute_sentiment

    df = _spot([
        {"symbol": "sh600000", "pct_chg": 5.0},    # 涨
        {"symbol": "sh600001", "pct_chg": -3.0},   # 跌
        {"symbol": "sh600002", "pct_chg": 0.0},    # 平
        {"symbol": "sh600003", "pct_chg": 10.0},   # 主板涨停（≥9.5）
        {"symbol": "sz300001", "pct_chg": 19.9},   # 创业板涨停（≥19.5）
        {"symbol": "sh600004", "pct_chg": -10.0},  # 主板跌停
    ])
    s = compute_sentiment(df)

    assert s["total"] == 6
    assert s["up"] == 3 and s["down"] == 2 and s["flat"] == 1
    assert s["limit_up"] == 2      # 600003 + 300001
    assert s["limit_down"] == 1    # 600004
    assert s["temperature"] == round(3 / 5 * 100)  # 上涨/活跃 = 3/5 = 60
    assert s["adv_decline_ratio"] == round(3 / 2, 2)
    assert s["profit_effect"] == round(3 / 6, 4)


def test_compute_sentiment_empty_neutral():
    """空快照 → 温度中性 50，家数全 0。"""
    from app.services.market_sentiment import compute_sentiment

    s = compute_sentiment(_spot([]))
    assert s["total"] == 0
    assert s["temperature"] == 50
    assert s["up"] == 0 and s["limit_up"] == 0


def test_compute_sentiment_all_up_hot():
    """全涨 → 温度 100。"""
    from app.services.market_sentiment import compute_sentiment

    s = compute_sentiment(_spot([
        {"symbol": "sh600000", "pct_chg": 3.0},
        {"symbol": "sh600001", "pct_chg": 1.5},
    ]))
    assert s["temperature"] == 100
    assert s["down"] == 0


def test_snapshot_sentiment_sync_writes_history(monkeypatch):
    """snapshot 读 spot 快照 → 算情绪 → 写 Redis 历史 hash（mock sync redis）。"""
    import redis as sync_redis

    from app.services import market_sentiment
    from app.services.screener import SNAPSHOT_KEY

    spot_json = _spot([
        {"symbol": "sh600000", "pct_chg": 5.0},
        {"symbol": "sh600001", "pct_chg": -3.0},
    ]).to_json(orient="records")
    store: dict[tuple[str, str], str] = {}

    class _FakeR:
        def get(self, k):
            return spot_json if k == SNAPSHOT_KEY else None

        def hset(self, k, field, value):
            store[(k, field)] = value

        def close(self):
            pass

    monkeypatch.setattr(sync_redis, "from_url", lambda *a, **k: _FakeR())

    res = market_sentiment.snapshot_sentiment_sync()
    assert res["ok"] is True
    assert any(k[0] == market_sentiment._SENTIMENT_HIST_KEY for k in store)


def test_snapshot_sentiment_sync_no_snapshot(monkeypatch):
    """无 spot 快照 → ok False。"""
    import redis as sync_redis

    from app.services import market_sentiment

    class _FakeR:
        def get(self, k):
            return None

        def close(self):
            pass

    monkeypatch.setattr(sync_redis, "from_url", lambda *a, **k: _FakeR())
    assert market_sentiment.snapshot_sentiment_sync()["ok"] is False


# ── 连板梯队（v0.8.37）───────────────────────────────────────────────────


def _limit_kline(boards: int, base: float = 10.0) -> pd.DataFrame:
    """主板 N 连板日 K：前 40 横盘，末 N 根精确涨停（×1.1）。"""
    closes = [base] * 40
    last = base
    for _ in range(boards):
        last = round(last * 1.1, 2)
        closes.append(last)
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {"close": closes, "high": closes, "low": [c * 0.97 for c in closes]}, index=idx
    )


def test_limit_up_ladder_buckets_and_leaders(fake_arctic, monkeypatch):
    """3 连板 + 1 板 + 普通票：分档计数 + 最高板 3 + 高板龙头含 3 板。"""
    from app.db.arctic import get_library
    from app.services import market_sentiment, short_term

    monkeypatch.setattr(short_term, "_name_map", lambda syms: {})
    lib = get_library("bar_1d")
    lib.write("sh600001", _limit_kline(3))
    lib.write("sh600002", _limit_kline(1))
    lib.write("sz000099", _limit_kline(0))  # 纯横盘，无涨停

    res = market_sentiment.compute_limit_up_ladder()
    assert res["ready"] is True
    assert res["max_board"] == 3
    assert res["total"] == 2  # 600001 + 600002
    buckets = {b["label"]: b["count"] for b in res["ladder"]}
    assert buckets["3板"] == 1 and buckets["1板"] == 1
    assert any(lead["boards"] == 3 for lead in res["leaders"])
    # 1 板不入龙头（仅 ≥2 板）
    assert all(lead["boards"] >= 2 for lead in res["leaders"])


def test_limit_up_ladder_empty_lib(fake_arctic):
    """空库 → ready False。"""
    from app.services.market_sentiment import compute_limit_up_ladder

    assert compute_limit_up_ladder()["ready"] is False


# ── 北向资金流向（v0.8.37）───────────────────────────────────────────────


def test_parse_north_net_sums_north_channels():
    """沪股通 + 深股通净买额求和；南向（港股通）不计。"""
    from app.services.market_sentiment import _parse_north_net

    df = pd.DataFrame([
        {"资金方向": "沪股通", "成交净买额": 30.5},
        {"资金方向": "深股通", "成交净买额": 20.0},
        {"资金方向": "港股通", "成交净买额": -10.0},
    ])
    assert _parse_north_net(df) == 50.5


def test_parse_north_net_unit_yuan_to_yi():
    """单位为元时转亿元。"""
    from app.services.market_sentiment import _parse_north_net

    df = pd.DataFrame([{"资金方向": "北向", "成交净买额": 5_050_000_000.0}])
    assert _parse_north_net(df) == 50.5


def test_parse_north_net_bad_structure():
    """字段不符 / 空 → None（触发降级）。"""
    from app.services.market_sentiment import _parse_north_net

    assert _parse_north_net(pd.DataFrame([{"foo": 1}])) is None
    assert _parse_north_net(None) is None


def test_fetch_north_flow_sync_writes(monkeypatch):
    """拉取成功 → 解析净流入并写 Redis 当日 + 历史（mock akshare + redis）。"""
    import akshare as ak
    import redis as sync_redis

    from app.services import market_sentiment

    monkeypatch.setattr(
        ak, "stock_hsgt_fund_flow_summary_em",
        lambda: pd.DataFrame([
            {"资金方向": "沪股通", "成交净买额": 30.0},
            {"资金方向": "深股通", "成交净买额": 20.0},
        ]),
    )
    store: dict = {}

    class _FakeR:
        def set(self, k, v, ex=None):
            store[k] = v

        def hset(self, k, f, v):
            store[(k, f)] = v

        def close(self):
            pass

    monkeypatch.setattr(sync_redis, "from_url", lambda *a, **k: _FakeR())

    res = market_sentiment.fetch_north_flow_sync()
    assert res["ok"] is True and res["net"] == 50.0
    assert market_sentiment._NORTH_TODAY_KEY in store


def test_fetch_north_flow_sync_degrades(monkeypatch):
    """接口抛错 → ok False（降级，不抛异常）。"""
    import akshare as ak

    from app.services import market_sentiment

    def _boom():
        raise RuntimeError("hsgt api removed")

    monkeypatch.setattr(ak, "stock_hsgt_fund_flow_summary_em", _boom)
    assert market_sentiment.fetch_north_flow_sync()["ok"] is False
