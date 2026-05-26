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
