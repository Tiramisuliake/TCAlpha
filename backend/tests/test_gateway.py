"""Gateway 抽象（Phase 9 起步）单元测试。"""
from __future__ import annotations

import pytest

from app.core.gateway import BaseGateway, create_gateway
from app.core.sim_gateway import SimGateway


def test_sim_gateway_implements_base():
    """SimGateway 是 BaseGateway 的实现；默认生命周期方法 no-op 可调用。"""
    assert issubclass(SimGateway, BaseGateway)
    gw = SimGateway(user_id=1)
    assert isinstance(gw, BaseGateway)
    gw.connect()
    gw.disconnect()
    gw.subscribe("sh600000")


def test_create_gateway_default_sim():
    """工厂默认（settings.gateway_type=sim）返回 SimGateway，并透传 user/strategy。"""
    gw = create_gateway(user_id=1, strategy_id=2)
    assert isinstance(gw, SimGateway)
    assert gw.user_id == 1
    assert gw.strategy_id == 2


def test_create_gateway_explicit_type_overrides():
    """显式传 gateway_type 覆盖配置（大小写不敏感）。"""
    gw = create_gateway(user_id=1, gateway_type="SIM")
    assert isinstance(gw, SimGateway)


def test_create_gateway_unknown_type_raises():
    """未注册的网关类型 → ValueError 并列出可用类型。"""
    with pytest.raises(ValueError, match="unknown gateway type: qmt"):
        create_gateway(user_id=1, gateway_type="qmt")


def test_base_gateway_match_default_noop():
    """BaseGateway.match 默认 no-op（实盘撮合在券商侧）。"""

    class _Dummy(BaseGateway):
        name = "DUMMY"

        def send_order(self, symbol, direction, offset, price, volume) -> int:
            return 0

        def cancel_order(self, order_id) -> bool:
            return False

        def get_position(self, symbol) -> int:
            return 0

    assert _Dummy().match(next_bar=None) == []
