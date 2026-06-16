"""每日收盘短线选股推送任务（screen_tasks）单元测试。

mock scan_short_term 与 publish_event，不连真 ArcticDB / Redis。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.tasks import screen_tasks


@pytest.fixture
def _capture(monkeypatch):
    """收集 publish_event 调用。"""
    calls: list[dict] = []

    def fake_publish(event_type, payload=None, *, user_id=None, level="info"):
        calls.append({"type": event_type, "payload": payload, "level": level})

    monkeypatch.setattr(screen_tasks, "publish_event", fake_publish)
    return calls


def _stub_scan(monkeypatch, result: dict):
    """替换 scan_short_term（task 内函数级 import → patch 源模块属性）。"""
    from app.services import short_term

    monkeypatch.setattr(short_term, "scan_short_term", lambda filters: result)


def test_daily_scan_pushes_on_hit(monkeypatch, _capture):
    """命中 → publish_event("screen.short_term") 且 payload 含形态/命中数/TOP1。"""
    _stub_scan(monkeypatch, {
        "ready": True,
        "count": 2,
        "candidates": [
            {"code": "600519", "name": "贵州茅台", "price": 1688.0, "score": 1.85},
            {"code": "000001", "name": "平安银行", "price": 12.3, "score": 1.2},
        ],
    })

    res = screen_tasks.scan_short_term_daily.run(pattern="volume_breakout", top=10, force=True)

    assert res["status"] == "ok" and res["count"] == 2
    assert len(_capture) == 1
    evt = _capture[0]
    assert evt["type"] == "screen.short_term"
    assert evt["payload"]["形态"] == "放量突破"
    assert evt["payload"]["命中"] == "2 只"
    assert "600519" in evt["payload"]["TOP1"]


def test_daily_scan_no_push_when_empty(monkeypatch, _capture):
    """无命中 → 不推送（减噪）。"""
    _stub_scan(monkeypatch, {"ready": True, "count": 0, "candidates": []})

    res = screen_tasks.scan_short_term_daily.run(force=True)

    assert res["status"] == "ok" and res["count"] == 0
    assert _capture == []


def test_daily_scan_skips_when_no_data(monkeypatch, _capture):
    """无历史 K 线（ready False）→ skip，不推送。"""
    _stub_scan(monkeypatch, {"ready": False, "count": 0, "candidates": []})

    res = screen_tasks.scan_short_term_daily.run(force=True)

    assert res["status"] == "skipped" and res["reason"] == "no_data"
    assert _capture == []


def test_daily_scan_skips_on_weekend(monkeypatch, _capture):
    """周末（force=False）→ skip，不触发扫描。"""
    # 2026-06-13 是周六
    monkeypatch.setattr(screen_tasks, "now_cn", lambda: datetime(2026, 6, 13, 15, 5))

    def _boom(filters):
        raise AssertionError("scan_short_term should not be called on weekend")

    from app.services import short_term

    monkeypatch.setattr(short_term, "scan_short_term", _boom)

    res = screen_tasks.scan_short_term_daily.run(force=False)

    assert res["status"] == "skipped" and res["reason"] == "weekend"
    assert _capture == []


# ── 多形态合并推送（v0.8.14）─────────────────────────────────────────────


def _stub_scan_by_pattern(monkeypatch, mapping: dict[str, dict]):
    """按 filters["pattern"] 返回不同结果。"""
    from app.services import short_term

    def fake(filters):
        return mapping[filters["pattern"]]

    monkeypatch.setattr(short_term, "scan_short_term", fake)


def test_multi_pattern_pushes_one_combined_event(monkeypatch, _capture):
    """多形态命中 → 仅推一条事件，payload 含各有命中形态的行。"""
    _stub_scan_by_pattern(monkeypatch, {
        "volume_breakout": {"ready": True, "candidates": [
            {"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]},
        "ma_long": {"ready": True, "candidates": [{"code": "300750", "name": "宁德时代"}]},
        "pullback": {"ready": True, "candidates": []},  # 无命中
        "limit_up": {"ready": True, "candidates": [{"code": "600000", "name": "浦发银行"}]},
    })

    res = screen_tasks.scan_multi_pattern_daily.run(top=5, force=True)

    assert res["status"] == "ok"
    assert res["count"] == 4  # 2 + 1 + 0 + 1
    assert len(_capture) == 1
    payload = _capture[0]["payload"]
    assert "放量突破" in payload and "2 只" in payload["放量突破"]
    assert "均线多头" in payload
    assert "涨停打板" in payload
    assert "回踩企稳" not in payload  # 无命中的形态不列


def test_multi_pattern_no_push_when_all_empty(monkeypatch, _capture):
    """全形态零命中 → 不推送。"""
    empty = {"ready": True, "candidates": []}
    _stub_scan_by_pattern(monkeypatch, {p: empty for p in
                                        ("volume_breakout", "ma_long", "pullback", "limit_up")})

    res = screen_tasks.scan_multi_pattern_daily.run(force=True)

    assert res["status"] == "ok" and res["count"] == 0
    assert _capture == []


def test_multi_pattern_skips_when_no_data(monkeypatch, _capture):
    """全形态 ready False（无 K 线）→ skip。"""
    nodata = {"ready": False, "candidates": []}
    _stub_scan_by_pattern(monkeypatch, {p: nodata for p in
                                        ("volume_breakout", "ma_long", "pullback", "limit_up")})

    res = screen_tasks.scan_multi_pattern_daily.run(force=True)

    assert res["status"] == "skipped" and res["reason"] == "no_data"
    assert _capture == []


def test_multi_pattern_weekend_skip(monkeypatch, _capture):
    """周末 force=False → skip。"""
    monkeypatch.setattr(screen_tasks, "now_cn", lambda: datetime(2026, 6, 13, 15, 5))  # 周六

    res = screen_tasks.scan_multi_pattern_daily.run(force=False)

    assert res["status"] == "skipped" and res["reason"] == "weekend"
    assert _capture == []
