"""模拟资金账户（SimGateway 资金约束）。

每用户一行（user_id 唯一）。开仓扣款 / 平仓入账由 SimGateway 在撮合时
维护；余额不足时拒单。重置即 balance 回到 init_capital。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, UniqueConstraint, func
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


class SimEquitySnapshot(Base):
    """模拟账户每日净值快照（收盘后 beat 记录，供净值曲线复盘）。

    total_asset = balance（现金）+ position_value（持仓市值，按最新收盘价；
    无行情时用持仓成本兜底）。每用户每日一行（user_id + dt 唯一）。
    """

    __tablename__ = "sim_equity_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "dt", name="uq_equity_user_dt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dt: Mapped[date] = mapped_column(Date, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    position_value: Mapped[float] = mapped_column(Float, default=0.0)
    total_asset: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
