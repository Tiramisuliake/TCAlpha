"""SimGateway 单元测试（B3）。

依赖 sync_db fixture（SQLite in-memory + 替换 SyncSessionLocal）。
publish_order 走 monkeypatch 收集消息，不连真 Redis。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core import sim_gateway as gw_mod
from app.core.sim_gateway import SimGateway


@pytest.fixture
def gateway(sync_db, monkeypatch):
    """SimGateway 实例 + 收集 publish_order 调用。"""
    published: list[dict] = []

    def fake_publish(user_id: int, order_dict: dict) -> None:
        published.append({"user_id": user_id, **order_dict})

    monkeypatch.setattr(gw_mod, "publish_order", fake_publish)

    g = SimGateway(user_id=1, strategy_id=1)
    g._published = published  # 测试用
    return g


def _bar(make_bar, *, symbol="sh600000", open_=10.0):
    return make_bar(datetime(2025, 1, 2, tzinfo=UTC), symbol=symbol, open_=open_)


def test_send_order_creates_submitted(gateway):
    """下单 → status=submitted，publish 触发一次。"""
    oid = gateway.send_order("sh600000", direction="long", offset="open",
                             price=10.0, volume=200)
    assert oid > 0
    assert len(gateway._published) == 1
    msg = gateway._published[0]
    assert msg["status"] == "submitted"
    assert msg["volume"] == 200


def test_send_order_volume_rounded_to_lot(gateway):
    """下单量被 round 到 100 倍数；不足 100 强制设为 100。"""
    gateway.send_order("sh600000", "long", "open", 10.0, 250)
    assert gateway._published[-1]["volume"] == 200  # 250 // 100 * 100

    gateway.send_order("sh600000", "long", "open", 10.0, 50)
    assert gateway._published[-1]["volume"] == 100  # min 100


def test_match_fills_at_next_bar_open(gateway, make_bar):
    """submitted 订单被 next_bar 开盘价 fill；status→filled；持仓更新。"""
    gateway.send_order("sh600000", "long", "open", price=999.0, volume=100)

    bar = _bar(make_bar, open_=10.5)
    filled = gateway.match(bar)
    assert len(filled) == 1

    pos = gateway.get_position("sh600000")
    assert pos == 100

    last = gateway._published[-1]
    assert last["status"] == "filled"
    assert last["price"] == pytest.approx(10.5)  # 用 next_bar.open
    assert last["filled_volume"] == 100


def test_position_net_long_short_offset(gateway, make_bar):
    """聚合持仓：开多 +、平多 -、开空 -、平空 +。"""
    bar = _bar(make_bar, open_=10.0)

    # 开多 200 → +200
    gateway.send_order("sh600000", "long", "open", 10.0, 200)
    gateway.match(bar)
    assert gateway.get_position("sh600000") == 200

    # 平多 100 → +100
    gateway.send_order("sh600000", "long", "close", 10.0, 100)
    gateway.match(bar)
    assert gateway.get_position("sh600000") == 100

    # 再开空 100 → 0（多 100 - 空开 100）
    gateway.send_order("sh600000", "short", "open", 10.0, 100)
    gateway.match(bar)
    assert gateway.get_position("sh600000") == 0
