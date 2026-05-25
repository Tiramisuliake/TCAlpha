"""模拟交易订单（SimGateway 落库）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class SimOrder(Base):
    __tablename__ = "sim_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(8))   # long/short
    offset: Mapped[str] = mapped_column(String(8))      # open/close
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    filled_volume: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="submitted")
    # submitted / partial / filled / cancelled / rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
