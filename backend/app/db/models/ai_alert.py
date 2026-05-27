"""AI 盯盘告警结果。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class AiAlert(Base):
    __tablename__ = "ai_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    # info / warn / danger
    level: Mapped[str] = mapped_column(String(16), default="info", index=True)
    # 简短信号摘要（"短线超买，建议减仓" 等）
    signal: Mapped[str] = mapped_column(String(256))
    # AI 给的理由（完整段落）
    reason: Mapped[str] = mapped_column(Text, default="")
    # 喂给 AI 的指标快照，便于复盘
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    acked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
