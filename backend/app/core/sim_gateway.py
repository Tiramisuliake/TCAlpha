"""模拟撮合网关（Phase 4）。

同步版本，供 Celery worker 内使用（PG SyncSession）。
订单写 sim_orders，按 next bar 开盘价撮合，结果发 Redis pub/sub。
"""
from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.gateway import BaseGateway
from app.core.pubsub import publish_order
from app.db.models.account import SimAccount
from app.db.models.order import SimOrder
from app.db.postgres import SyncSessionLocal


class SimGateway(BaseGateway):
    name = "SIM"
    COMMISSION_RATE = 0.0003
    STAMP_DUTY = 0.001   # 卖出印花税

    def __init__(self, user_id: int, strategy_id: int | None = None) -> None:
        self.user_id = user_id
        self.strategy_id = strategy_id

    # ── 资金账户 ──────────────────────────────────────────────────────

    def _get_or_create_account(self, db: Session) -> SimAccount:
        """懒创建资金账户（初始资金走 settings.sim_init_capital）。"""
        acct = db.execute(
            select(SimAccount).where(SimAccount.user_id == self.user_id)
        ).scalar_one_or_none()
        if acct is None:
            from app.config import settings

            acct = SimAccount(
                user_id=self.user_id,
                balance=settings.sim_init_capital,
                init_capital=settings.sim_init_capital,
            )
            db.add(acct)
            db.flush()
        return acct

    def get_balance(self) -> float:
        with SyncSessionLocal() as db:
            acct = self._get_or_create_account(db)
            balance = acct.balance
            db.commit()
        return balance

    # ── 下单 ──────────────────────────────────────────────────────────

    def send_order(
        self,
        symbol: str,
        direction: str,
        offset: str,
        price: float,
        volume: int,
    ) -> int:
        """创建一条 submitted 订单，返回 order.id。

        开仓单按委托价预校验资金（估算含手续费），余额不足直接 rejected
        —— 成交价以撮合时为准，撮合时还会按实际价复核一次。
        """
        # 最小 100 股单位
        volume = max((volume // 100) * 100, 100)

        with SyncSessionLocal() as db:
            status = "submitted"
            if offset == "open":
                acct = self._get_or_create_account(db)
                est_cost = price * volume * (1 + self.COMMISSION_RATE)
                if acct.balance < est_cost:
                    status = "rejected"

            order = SimOrder(
                user_id=self.user_id,
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                filled_volume=0,
                status=status,
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            order_id = order.id
            self._publish(db, order)

        if status == "rejected":
            logger.warning(
                "SimGateway.send_order rejected (insufficient balance): {} {} vol={} @ {}",
                symbol, offset, volume, price,
            )
        else:
            logger.info(
                "SimGateway.send_order: id={} {} {} {} vol={}",
                order_id, symbol, direction, offset, volume,
            )
        return order_id

    # ── 撮合 ──────────────────────────────────────────────────────────

    def match(self, next_bar) -> list[int]:
        """用 next_bar 开盘价撮合所有 submitted 订单，返回已成交 order_id 列表。

        资金账户随成交结算：开仓扣 现金 + 手续费（实际价复核，不足拒单）；
        平仓入 现金 - 手续费 - 印花税（卖出）。
        """
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
            acct = self._get_or_create_account(db) if orders else None
            for order in orders:
                exec_price = float(next_bar.open_price)
                if order.offset == "open":
                    cost = exec_price * order.volume * (1 + self.COMMISSION_RATE)
                    if acct.balance < cost:
                        # 委托后价格上行导致资金不够 → 拒单
                        order.status = "rejected"
                        order.updated_at = datetime.now(tz=UTC)
                        logger.warning(
                            "SimGateway.match rejected (insufficient balance): id={} need={:.2f} have={:.2f}",
                            order.id, cost, acct.balance,
                        )
                        continue
                    acct.balance -= cost
                else:
                    proceeds = exec_price * order.volume * (
                        1 - self.COMMISSION_RATE - self.STAMP_DUTY
                    )
                    acct.balance += proceeds

                order.price = exec_price
                order.filled_volume = order.volume
                order.status = "filled"
                order.updated_at = datetime.now(tz=UTC)
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
            order.updated_at = datetime.now(tz=UTC)
            db.commit()
            db.refresh(order)
            self._publish(db, order)
        return True

    # ── 持仓 ──────────────────────────────────────────────────────────

    def get_position(self, symbol: str) -> int:
        """从已成交订单聚合净持仓（多头为正）。

        在 DB 端按 direction/offset 分组求和（≤4 行），避免拉全部成交订单到内存聚合。
        """
        stmt = select(
            SimOrder.direction,
            SimOrder.offset,
            func.sum(SimOrder.filled_volume),
        ).where(
            SimOrder.user_id == self.user_id,
            SimOrder.symbol == symbol,
            SimOrder.status == "filled",
        )
        if self.strategy_id is not None:
            stmt = stmt.where(SimOrder.strategy_id == self.strategy_id)
        stmt = stmt.group_by(SimOrder.direction, SimOrder.offset)

        with SyncSessionLocal() as db:
            rows = db.execute(stmt).all()

        pos = 0
        for direction, offset, vol in rows:
            sign = 1 if direction == "long" else -1
            sign *= 1 if offset == "open" else -1
            pos += sign * int(vol or 0)
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
