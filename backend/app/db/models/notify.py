"""通知中心：规则 + 推送历史（Phase 5 Step 1）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class NotifyRule(Base):
    """用户级通知规则。"""

    __tablename__ = "notify_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))

    # 匹配事件类型，支持通配符："strategy.*" / "ai.alert.warn"
    match_types: Mapped[list] = mapped_column(JSON, default=list)
    # 附加过滤条件：{"symbol": ["sh600000"], "min_level": "warn"}
    match_filters: Mapped[dict] = mapped_column(JSON, default=dict)

    # 推送渠道：v0.5.1 仅支持 "feishu"，预留 "email" / "ws" / "dingtalk"
    channels: Mapped[list] = mapped_column(JSON, default=list)

    # 飞书机器人配置（用户级，每个用户自己的群）
    feishu_webhook: Mapped[str] = mapped_column(Text, default="")
    feishu_secret: Mapped[str] = mapped_column(String(128), default="")

    # 静音时段，格式 "HH:MM-HH:MM"，跨天用 "22:00-08:00"
    quiet_hours: Mapped[str] = mapped_column(String(16), default="")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotifyLog(Base):
    """每次推送结果记录，便于用户排查"为什么没收到"。"""

    __tablename__ = "notify_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("notify_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_msg: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
