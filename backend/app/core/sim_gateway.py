"""模拟撮合网关（Phase 4 实现）。

订单写 sim_orders 表，按 next bar 撮合 → emit fill 事件到 Redis。
"""
from __future__ import annotations


class SimGateway:
    name = "SIM"

    def connect(self) -> None:
        pass  # TODO Phase 4

    def disconnect(self) -> None:
        pass

    def send_order(self, symbol: str, direction: str, offset: str, price: float, volume: int) -> str:
        raise NotImplementedError("Phase 4")

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError("Phase 4")

    def subscribe(self, symbol: str) -> None:
        pass
