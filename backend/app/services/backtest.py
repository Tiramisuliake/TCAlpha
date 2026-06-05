"""回测业务逻辑（Phase 3）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.backtest import BacktestJob, BacktestTrade, ParamSweepJob
from app.schemas.backtest import (
    BacktestStatusOut,
    BacktestSubmit,
    BacktestTradeOut,
    SweepStatusOut,
    SweepSubmit,
)


async def submit_backtest(
    db: AsyncSession, user_id: int, payload: BacktestSubmit
) -> BacktestStatusOut:
    """创建 BacktestJob，提交 Celery 任务，返回状态。"""
    job = BacktestJob(
        user_id=user_id,
        name=payload.name,
        class_name=payload.class_name,
        symbol=payload.symbol,
        params=payload.params,
        start_date=payload.start_date,
        end_date=payload.end_date,
        init_capital=payload.init_capital,
        commission_rate=payload.commission_rate,
        slippage=payload.slippage,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.tasks.backtest_tasks import run_backtest

    result = run_backtest.delay(job.id)
    job.celery_task_id = result.id
    job.status = "running"
    await db.commit()

    return BacktestStatusOut(job_id=job.id, status=job.status)


async def get_backtest_status(
    db: AsyncSession, job_id: int, user_id: int
) -> BacktestStatusOut | None:
    stmt = select(BacktestJob).where(
        BacktestJob.id == job_id, BacktestJob.user_id == user_id
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        return None
    return BacktestStatusOut(job_id=job.id, status=job.status, result=job.result, error=job.error)


async def list_backtests(db: AsyncSession, user_id: int) -> list[BacktestStatusOut]:
    stmt = select(BacktestJob).where(BacktestJob.user_id == user_id).order_by(
        BacktestJob.created_at.desc()
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        BacktestStatusOut(job_id=r.id, status=r.status, result=r.result, error=r.error)
        for r in rows
    ]


async def get_trades(
    db: AsyncSession, job_id: int, user_id: int
) -> list[BacktestTradeOut] | None:
    # 先验证 job 属于当前用户
    job_stmt = select(BacktestJob.id).where(
        BacktestJob.id == job_id, BacktestJob.user_id == user_id
    )
    if not (await db.execute(job_stmt)).scalar_one_or_none():
        return None

    stmt = select(BacktestTrade).where(BacktestTrade.job_id == job_id).order_by(
        BacktestTrade.dt
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [BacktestTradeOut.model_validate(r) for r in rows]


async def submit_sweep(
    db: AsyncSession, user_id: int, payload: SweepSubmit
) -> SweepStatusOut:
    """创建 ParamSweepJob，提交扫参 Celery 任务，返回状态。"""
    job = ParamSweepJob(
        user_id=user_id,
        name=payload.name,
        class_name=payload.class_name,
        symbol=payload.symbol,
        param_grid=payload.param_grid,
        target=payload.target,
        start_date=payload.start_date,
        end_date=payload.end_date,
        init_capital=payload.init_capital,
        commission_rate=payload.commission_rate,
        slippage=payload.slippage,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.tasks.backtest_tasks import run_param_sweep

    result = run_param_sweep.delay(job.id)
    job.celery_task_id = result.id
    job.status = "running"
    await db.commit()

    return SweepStatusOut(job_id=job.id, status=job.status)


async def get_sweep_status(
    db: AsyncSession, job_id: int, user_id: int
) -> SweepStatusOut | None:
    stmt = select(ParamSweepJob).where(
        ParamSweepJob.id == job_id, ParamSweepJob.user_id == user_id
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        return None
    return SweepStatusOut(job_id=job.id, status=job.status, result=job.result, error=job.error)


async def list_sweeps(db: AsyncSession, user_id: int) -> list[SweepStatusOut]:
    stmt = select(ParamSweepJob).where(ParamSweepJob.user_id == user_id).order_by(
        ParamSweepJob.created_at.desc()
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        SweepStatusOut(job_id=r.id, status=r.status, result=r.result, error=r.error)
        for r in rows
    ]
