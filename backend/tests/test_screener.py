"""选股器 screen 过滤单元测试（mock Redis 快照）。"""
from __future__ import annotations

import pandas as pd


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
