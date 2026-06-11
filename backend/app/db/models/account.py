"""模拟资金账户（SimGateway 资金约束）。

每用户一行（user_id 唯一）。开仓扣款 / 平仓入账由 SimGateway 在撮合时
维护；余额不足时拒单。重置即 balance 回到 init_capital。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class SimAccount(Base):
    __tablename__ = "sim_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    balance: Mapped[float] = mapped_column(Float, default=1_000_000.0)       # 可用现金
    init_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0)  # 初始资金（重置基准）

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
