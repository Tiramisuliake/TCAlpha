"""模拟撮合网关（Phase 4）。

同步版本，供 Celery worker 内使用（PG SyncSession）。
订单写 sim_orders，按 next bar 开盘价撮合，结果发 Redis pub/sub。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pubsub import order_channel, publish_order
from app.db.models.order import SimOrder
from app.db.postgres import SyncSessionLocal


class SimGateway:
    name = "SIM"
    COMMISSION_RATE = 0.0003
    STAMP_DUTY = 0.001   # 卖出印花税

    def __init__(self, user_id: int, strategy_id: int | None = None) -> None:
        self.user_id = user_id
        self.strategy_id = strategy_id

    # ── 下单 ──────────────────────────────────────────────────────────

    def send_order(
        self,
        symbol: str,
        direction: str,
        offset: str,
        price: float,
        volume: int,
    ) -> int:
        """创建一条 submitted 订单，返回 order.id。"""
        # 最小 100 股单位
        volume = max((volume // 100) * 100, 100)

        with SyncSessionLocal() as db:
            order = SimOrder(
                user_id=self.user_id,
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                filled_volume=0,
                status="submitted",
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            order_id = order.id
            self._publish(db, order)

        logger.info("SimGateway.send_order: id={} {} {} {} vol={}", order_id, symbol, direction, offset, volume)
        return order_id

    # ── 撮合 ──────────────────────────────────────────────────────────

    def match(self, next_bar) -> list[int]:
        """用 next_bar 开盘价撮合所有 submitted 订单，返回已成交 order_id 列表。"""
        filled_ids: list[int] = []
        with SyncSessionLocal() as db:
            stmt = select(SimOrder).where(
                SimOrder.symbol == next_bar.symbol,
                SimOrder.status == "submitted",
                SimOrder.user_id == self.user_id,
            )
            if self.strategy_id is not None:
                stmt = stmt.where(SimOrder.strategy_id == self.strategy_id)

            orders = db.execute(stmt).scalars().all()
            for order in orders:
                exec_price = float(next_bar.open_price)
                order.price = exec_price
                order.filled_volume = order.volume
                order.status = "filled"
                order.updated_at = datetime.now(tz=timezone.utc)
                filled_ids.append(order.id)
            db.commit()

            for order in orders:
                db.refresh(order)
                self._publish(db, order)
                logger.info(
                    "SimGateway.match filled: id={} {} price={} vol={}",
                    order.id, order.symbol, order.price, order.filled_volume,
                )

        return filled_ids

    def cancel_order(self, order_id: int) -> bool:
        with SyncSessionLocal() as db:
            order = db.get(SimOrder, order_id)
            if not order or order.status != "submitted":
                return False
            order.status = "cancelled"
            order.updated_at = datetime.now(tz=timezone.utc)
            db.commit()
            db.refresh(order)
            self._publish(db, order)
        return True

    # ── 持仓 ──────────────────────────────────────────────────────────

    def get_position(self, symbol: str) -> int:
        """从已成交订单聚合净持仓（多头为正）。"""
        with SyncSessionLocal() as db:
            stmt = select(SimOrder).where(
                SimOrder.user_id == self.user_id,
                SimOrder.symbol == symbol,
                SimOrder.status == "filled",
            )
            if self.strategy_id is not None:
                stmt = stmt.where(SimOrder.strategy_id == self.strategy_id)
            orders = db.execute(stmt).scalars().all()

        pos = 0
        for o in orders:
            sign = 1 if o.direction == "long" else -1
            sign *= 1 if o.offset == "open" else -1
            pos += sign * o.filled_volume
        return pos

    # ── 内部 ──────────────────────────────────────────────────────────

    def _publish(self, db: Session, order: SimOrder) -> None:  # noqa: ARG002
        try:
            publish_order(
                self.user_id,
                {
                    "id": order.id,
                    "symbol": order.symbol,
                    "direction": order.direction,
                    "offset": order.offset,
                    "price": order.price,
                    "volume": order.volume,
                    "filled_volume": order.filled_volume,
                    "status": order.status,
                    "strategy_id": order.strategy_id,
                },
            )
        except Exception as exc:
            logger.warning("publish_order failed: {}", exc)
