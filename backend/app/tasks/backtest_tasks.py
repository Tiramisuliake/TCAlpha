"""回测计算任务。"""
from __future__ import annotations

from loguru import logger

from app.core.event_bus import publish_event
from app.tasks.celery_app import celery_app


@celery_app.task(
    name="app.tasks.backtest_tasks.run_backtest",
    bind=True,
    time_limit=3600,
    soft_time_limit=3500,
)
def run_backtest(self, job_id: int) -> dict:
    """异步执行回测，结果写回 PG BacktestJob。"""
    logger.info("run_backtest start: job={} celery_task={}", job_id, self.request.id)
    publish_event("backtest.started", {"job_id": job_id})
    from app.core.backtest_engine import run

    try:
        result = run(job_id)
        publish_event("backtest.done", {"job_id": job_id, "result": result})
        return result
    except Exception as exc:
        publish_event(
            "backtest.failed",
            {"job_id": job_id, "exception": type(exc).__name__, "detail": str(exc)[:300]},
            level="danger",
        )
        raise


@celery_app.task(
    name="app.tasks.backtest_tasks.run_param_sweep",
    bind=True,
    time_limit=3600,
    soft_time_limit=3500,
)
def run_param_sweep(self, job_id: int) -> dict:
    """异步执行网格扫参，结果写回 PG ParamSweepJob。"""
    from datetime import UTC, datetime

    from app.core.backtest_engine import run_sweep
    from app.db.models.backtest import ParamSweepJob
    from app.db.postgres import SyncSessionLocal

    logger.info("run_param_sweep start: job={} celery_task={}", job_id, self.request.id)
    with SyncSessionLocal() as db:
        job = db.get(ParamSweepJob, job_id)
        if not job:
            raise ValueError(f"ParamSweepJob {job_id} not found")
        job.status = "running"
        # commit 前取出字段为局部变量，避免出 with 块后访问 detached ORM（见回测引擎同款处理）
        symbol = job.symbol
        class_name = job.class_name
        param_grid = job.param_grid
        start = str(job.start_date)
        end = str(job.end_date)
        target = job.target
        init_capital = job.init_capital
        commission_rate = job.commission_rate
        slippage = job.slippage
        period = getattr(job, "period", None) or "1d"
        oos_split = getattr(job, "oos_split", None)
        db.commit()

    try:
        result = run_sweep(
            symbol, class_name, param_grid, start, end,
            init_capital, commission_rate, slippage, target,
            period=period, oos_split=oos_split,
        )
        with SyncSessionLocal() as db:
            job = db.get(ParamSweepJob, job_id)
            if job is None:
                raise ValueError(f"ParamSweepJob {job_id} not found")
            job.status = "done"
            job.result = result
            job.finished_at = datetime.now(tz=UTC)
            db.commit()
        logger.info("run_param_sweep job={} done: {} combos", job_id, result.get("count"))
        return result
    except Exception as exc:
        logger.exception("run_param_sweep job={} failed: {}", job_id, exc)
        with SyncSessionLocal() as db:
            job = db.get(ParamSweepJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)[:1024]
                job.finished_at = datetime.now(tz=UTC)
                db.commit()
        raise
