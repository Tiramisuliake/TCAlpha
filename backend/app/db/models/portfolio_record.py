"""多因子组合回测结果存档（研究可追溯）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class PortfolioBacktestRecord(Base):
    """一次组合回测 / walk-forward 的配置 + 绩效快照（不存净值曲线，重跑可复现）。"""

    __tablename__ = "portfolio_backtest_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="backtest")  # backtest / walkforward
    config: Mapped[dict] = mapped_column(JSON, default=dict)   # weights / top_n / rebalance / lookback
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # 绩效指标快照
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
