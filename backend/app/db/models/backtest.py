"""回测任务 & 成交记录。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    class_name: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    init_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    commission_rate: Mapped[float] = mapped_column(Float, default=0.0003)
    slippage: Mapped[float] = mapped_column(Float, default=0.01)
    # 对比基准指数代码（000300 沪深300 / 000905 中证500 / 399006 创业板指 / 000016 上证50）
    benchmark: Mapped[str] = mapped_column(String(16), default="000300", server_default="000300")
    # K 线周期（1d / 60m / 30m / 15m / 5m / 1m），对应 ArcticDB bar_{period} 库
    period: Mapped[str] = mapped_column(String(8), default="1d", server_default="1d")

    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 总收益、最大回撤、夏普 等
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("backtest_jobs.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))  # long/short
    offset: Mapped[str] = mapped_column(String(8))     # open/close
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    dt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)  # 平仓时记


class ParamSweepJob(Base):
    """网格扫参任务：对 param_grid 笛卡尔积逐组回测，按 target 找最优参数。"""

    __tablename__ = "param_sweep_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    class_name: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    param_grid: Mapped[dict] = mapped_column(JSON, default=dict)  # {"fast":[5,10],"slow":[20,30]}
    target: Mapped[str] = mapped_column(String(32), default="sharpe")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    init_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    commission_rate: Mapped[float] = mapped_column(Float, default=0.0003)
    slippage: Mapped[float] = mapped_column(Float, default=0.01)
    # K 线周期（同 BacktestJob.period）
    period: Mapped[str] = mapped_column(String(8), default="1d", server_default="1d")
    # Walk-Forward 验证集占比（0~0.6，None = 不切分）
    oos_split: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {results, best, param_keys, ...}
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
