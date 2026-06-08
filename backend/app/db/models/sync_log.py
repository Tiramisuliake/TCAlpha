"""数据同步状态表（⑤）：记录每只票每周期的同步水位 / 失败原因。

每 (symbol, period) 唯一一条，下载任务成功更新水位、失败记录 error。
供运维查看同步健康度 + 增量下载推断起始日。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"
    __table_args__ = (
        UniqueConstraint("symbol", "period", name="uq_sync_logs_symbol_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    period: Mapped[str] = mapped_column(String(8), default="1d")
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / failed
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    rows: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
