"""交易网关抽象（Phase 9 起步）。

BaseGateway 定义统一交易契约：模拟盘 SimGateway 与未来实盘网关
（QMT / xtquant / easytrader …）实现同一接口，业务层（runtime / service）
只依赖抽象 + 工厂 —— 切实盘改配置 `GATEWAY_TYPE`，不改一行业务代码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class BaseGateway(ABC):
    """交易网关统一接口。

    - 生命周期 connect/disconnect：模拟盘 no-op，实盘网关在此建立/断开券商会话
    - subscribe：模拟盘行情由 runtime 主动拉 AKShare，实盘可覆写为推送注册
    - send_order/cancel_order/get_position：最小交易契约（抽象，必须实现）
    """

    name: str = ""

    # 以下三个为可选钩子，默认 no-op 是设计意图（模拟盘无会话/订阅概念），
    # 实盘网关按需覆写 —— 故豁免 B027（空方法应加 @abstractmethod）
    def connect(self) -> None:  # noqa: B027
        """建立会话（模拟盘 no-op）。"""

    def disconnect(self) -> None:  # noqa: B027
        """断开会话（模拟盘 no-op）。"""

    def subscribe(self, symbol: str) -> None:  # noqa: B027
        """订阅行情（模拟盘 no-op：行情由 runtime 拉取）。"""

    def match(self, next_bar) -> list[int]:
        """撮合钩子：模拟盘由 runtime 用新 bar 驱动撮合挂单；
        实盘撮合发生在券商侧，默认 no-op 返回空列表。"""
        return []

    @abstractmethod
    def send_order(
        self, symbol: str, direction: str, offset: str, price: float, volume: int
    ) -> int:
        """提交订单，返回本地订单 id。"""

    @abstractmethod
    def cancel_order(self, order_id: int) -> bool:
        """撤单，返回是否成功（非 submitted 状态返回 False）。"""

    @abstractmethod
    def get_position(self, symbol: str) -> int:
        """查询净持仓（多头为正）。"""


# ── 工厂：按配置选网关 ────────────────────────────────────────────────


def _make_sim(user_id: int, strategy_id: int | None) -> BaseGateway:
    from app.core.sim_gateway import SimGateway

    return SimGateway(user_id=user_id, strategy_id=strategy_id)


# 实盘网关接入时在此注册新类型（如 "qmt": _make_qmt），调用方零改动
_GATEWAY_FACTORIES: dict[str, Callable[[int, int | None], BaseGateway]] = {
    "sim": _make_sim,
}


def create_gateway(
    user_id: int, strategy_id: int | None = None, gateway_type: str | None = None
) -> BaseGateway:
    """按 `settings.gateway_type`（默认 sim）实例化网关；显式传参可覆盖。"""
    from app.config import settings

    gtype = (gateway_type or settings.gateway_type).lower()
    factory = _GATEWAY_FACTORIES.get(gtype)
    if factory is None:
        raise ValueError(
            f"unknown gateway type: {gtype} (available: {sorted(_GATEWAY_FACTORIES)})"
        )
    return factory(user_id, strategy_id)
