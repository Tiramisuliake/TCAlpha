"""交易网关抽象（预留实盘接入点）。

后期实盘接 XtquantGateway / QmtGateway 时实现此 Protocol。
"""
from __future__ import annotations

from typing import Protocol


class Gateway(Protocol):
    name: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def send_order(self, symbol: str, direction: str, offset: str, price: float, volume: int) -> str: ...
    def cancel_order(self, order_id: str) -> None: ...
    def subscribe(self, symbol: str) -> None: ...
