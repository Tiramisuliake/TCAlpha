"""股票基础信息表（元数据存 PG，K 线存 ArcticDB）。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # sh600000
    code: Mapped[str] = mapped_column(String(6), index=True)                  # 600000
    exchange: Mapped[str] = mapped_column(String(4))                           # SH / SZ / BJ
    name: Mapped[str] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
