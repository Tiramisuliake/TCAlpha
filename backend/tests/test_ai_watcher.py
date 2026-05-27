"""AI 盯盘核心测试（B4）。

覆盖：
- build_snapshot 在 fake 日 K 上算出合理的 MA / RSI / MACD
- _call_ai_json 用 mock 客户端返回合法/非法/异常三种 case
- watch_symbol 整条链路（mock AI）
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import ai_watcher
from app.services.ai_watcher import build_snapshot, _call_ai_json, watch_symbol


# ── build_snapshot ────────────────────────────────────────────────────


def test_build_snapshot_with_data(sample_bars_arctic):
    """200 根金叉死叉 fake K → snapshot 字段齐全，数值合理。"""
    snap = build_snapshot("sh600000")
    assert snap is not None
    assert snap["symbol"] == "sh600000"
    # MA5/10/20 应在合理价格区间
    assert 5 < snap["ma5"] < 20
    assert 5 < snap["ma10"] < 20
    assert 5 < snap["ma20"] < 20
    # RSI 在 [0, 100]
    assert 0 <= snap["rsi14"] <= 100
    # MACD 字段存在
    assert "macd_dif" in snap
    assert "macd_dea" in snap
    # 收盘价数组长度 5
    assert len(snap["recent_close_5d"]) == 5


def test_build_snapshot_no_data(tmp_arctic):
    """ArcticDB 没数据 → 返回 None。"""
    snap = build_snapshot("sh000000")
    assert snap is None


# ── _call_ai_json ─────────────────────────────────────────────────────


def _mock_openai_response(content: str):
    """构造 OpenAI 兼容 response 对象。"""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_call_ai_json_valid(monkeypatch):
    """AI 返回合法 JSON → 返回 WatchResult。"""
    fake_json = {
        "level": "warn",
        "signal": "RSI 超买，短线偏弱",
        "reason": "RSI 接近 80，MACD 高位顶背离，5 日涨幅过大，需谨慎",
    }
    mock_client = MagicMock()
    mock_create = MagicMock(return_value=_mock_openai_response(json.dumps(fake_json)))

    # client.chat.completions.create 是 async 的；用 AsyncMock
    from unittest.mock import AsyncMock
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_response(json.dumps(fake_json))
    )
    monkeypatch.setattr(ai_watcher, "get_client", lambda: mock_client)
    del mock_create  # noqa: F841 — 占位

    result = _call_ai_json({"symbol": "sh600000", "close": 10.0})
    assert result is not None
    assert result.level == "warn"
    assert "短线" in result.signal


def test_call_ai_json_invalid_json(monkeypatch):
    """AI 返回非 JSON → 返回 None。"""
    from unittest.mock import AsyncMock
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_response("不是合法 json")
    )
    monkeypatch.setattr(ai_watcher, "get_client", lambda: mock_client)

    result = _call_ai_json({"symbol": "sh600000"})
    assert result is None


def test_call_ai_json_validation_fail(monkeypatch):
    """AI 返回 JSON 但缺字段 / level 非法 → 返回 None。"""
    from unittest.mock import AsyncMock
    bad = {"level": "unknown_level", "signal": "x", "reason": "y"}
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_response(json.dumps(bad))
    )
    monkeypatch.setattr(ai_watcher, "get_client", lambda: mock_client)

    result = _call_ai_json({"symbol": "sh600000"})
    assert result is None


# ── watch_symbol（整条链路）────────────────────────────────────────────


def test_watch_symbol_full_path(sync_db, monkeypatch):
    """build_snapshot mock → AI mock → 落库 + publish_event。

    用 mock 跳过 ArcticDB，避免单例与 LMDB 句柄在测试间冲突。
    """
    from app.schemas.ai_alert import WatchResult

    fake_snapshot = {
        "symbol": "sh600000",
        "as_of": "2025-12-31",
        "close": 10.0,
        "recent_close_5d": [9.8, 9.9, 10.0, 10.1, 10.0],
        "ma5": 10.0, "ma10": 9.9, "ma20": 9.8,
        "rsi14": 55.0,
        "macd_dif": 0.05, "macd_dea": 0.03, "macd_hist": 0.04,
        "ret_5d_pct": 2.0, "ret_20d_pct": 5.0,
        "vol_avg_5d": 1_000_000, "vol_last": 1_200_000,
    }
    monkeypatch.setattr(ai_watcher, "build_snapshot", lambda *_a, **_kw: fake_snapshot)
    monkeypatch.setattr(
        ai_watcher,
        "_call_ai_json",
        lambda _snap: WatchResult(level="info", signal="无明显信号", reason="震荡区间"),
    )
    published = []
    monkeypatch.setattr(
        ai_watcher,
        "publish_event",
        lambda et, payload, **kw: published.append({"event_type": et, **payload, **kw}),
    )

    alert = watch_symbol(user_id=1, symbol="sh600000")
    assert alert is not None
    assert alert.level == "info"
    assert alert.symbol == "sh600000"

    assert len(published) == 1
    assert published[0]["event_type"] == "ai.alert.info"
    assert published[0]["user_id"] == 1


def test_watch_symbol_skip_when_no_snapshot(sync_db, monkeypatch):
    """build_snapshot 返回 None → watch_symbol 返回 None。"""
    monkeypatch.setattr(ai_watcher, "build_snapshot", lambda *_a, **_kw: None)
    alert = watch_symbol(user_id=1, symbol="sh999999")
    assert alert is None
