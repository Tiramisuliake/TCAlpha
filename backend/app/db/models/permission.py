"""RBAC 权限点（Phase 7 Step 1）。

code 命名约定：`<module>.<action>` 或 `<module>.<resource>.<action>`
例：strategy.create / strategy.start / sim.order.cancel / notify_rule.delete
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # 分类：strategy / sim / backtest / ai / notify / system
    category: Mapped[str] = mapped_column(String(32), default="", index=True)
    description: Mapped[str] = mapped_column(String(256), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
