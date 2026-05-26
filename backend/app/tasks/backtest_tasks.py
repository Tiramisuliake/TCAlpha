"""回测计算任务。"""
from __future__ import annotations

from loguru import logger

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
    from app.core.backtest_engine import run

    return run(job_id)
