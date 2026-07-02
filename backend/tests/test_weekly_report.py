"""AI 投研周报（services/weekly_report.py）单元测试。"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.utils.trading_period import now_cn


@pytest.fixture
def _fake_sentiment_redis(monkeypatch):
    """mock sync redis：情绪历史含本周 2 天。"""
    import redis as sync_redis

    today = now_cn().date()
    hist = {
        str(today - timedelta(days=1)): json.dumps(
            {"date": str(today - timedelta(days=1)), "temperature": 62, "limit_up": 45}
        ),
        str(today - timedelta(days=30)): json.dumps(  # 上月，不入周报
            {"date": str(today - timedelta(days=30)), "temperature": 30, "limit_up": 5}
        ),
    }

    class _FakeR:
        def hgetall(self, k):
            return hist

        def close(self):
            pass

    monkeypatch.setattr(sync_redis, "from_url", lambda *a, **k: _FakeR())


def test_collect_weekly_equity_and_sentiment(sync_db, _fake_sentiment_redis):
    """净值快照（本周 2 条）+ 情绪（仅本周）聚合正确。"""
    from app.db.models.account import SimEquitySnapshot
    from app.services.weekly_report import collect_weekly_sync

    today = now_cn().date()
    with sync_db() as db:
        db.add(SimEquitySnapshot(user_id=1, dt=today - timedelta(days=3), total_asset=1_000_000))
        db.add(SimEquitySnapshot(user_id=1, dt=today - timedelta(days=1), total_asset=1_050_000))
        db.add(SimEquitySnapshot(user_id=2, dt=today, total_asset=999.0))  # 他人不计
        db.commit()

    data = collect_weekly_sync(user_id=1)

    assert data["equity"]["start"] == 1_000_000
    assert data["equity"]["end"] == 1_050_000
    assert data["equity"]["change_pct"] == 5.0
    assert len(data["equity"]["points"]) == 2
    assert len(data["sentiment"]) == 1  # 仅本周的那条
    assert data["sentiment"][0]["temperature"] == 62


def test_build_weekly_html_contains_sections(sync_db, _fake_sentiment_redis):
    """HTML 含净值涨跌 / 情绪表 / AI 段落 / 免责声明。"""
    from app.services.weekly_report import build_weekly_html, collect_weekly_sync

    data = collect_weekly_sync(user_id=1)
    html = build_weekly_html(data, ai_text="本周市场偏暖。")

    assert "<!DOCTYPE html>" in html
    assert "投研周报" in html
    assert "账户净值周复盘" in html
    assert "市场情绪周走势" in html
    assert "本周市场偏暖。" in html
    assert "不构成投资建议" in html


def test_build_weekly_html_no_ai_degrades(sync_db, _fake_sentiment_redis):
    """无 AI 段落 → 显示降级提示，主体完整。"""
    from app.services.weekly_report import build_weekly_html, collect_weekly_sync

    html = build_weekly_html(collect_weekly_sync(user_id=1), ai_text="")
    assert "本期无综述" in html


async def test_ai_weekly_summary_degrades(monkeypatch):
    """AI 调用抛错 → 返回空串（不抛异常）。"""
    from app.services import ai as ai_svc
    from app.services.weekly_report import ai_weekly_summary

    async def _boom(messages, system=None, temperature=0.7):
        raise RuntimeError("no api key")
        yield  # pragma: no cover

    monkeypatch.setattr(ai_svc, "stream_chat", _boom)
    out = await ai_weekly_summary(
        {"equity": {"start": 1, "end": 1, "change_pct": 0.0}, "sentiment": []}
    )
    assert out == ""