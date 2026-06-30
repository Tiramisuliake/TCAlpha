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
