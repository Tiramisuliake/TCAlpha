"""回测计算任务。Phase 3 实现。"""
from __future__ import annotations

from loguru import logger

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.backtest_tasks.run_backtest", bind=True)
def run_backtest(self, job_id: int) -> dict:
    logger.info("[stub] run_backtest job={} task_id={} — Phase 3", job_id, self.request.id)
    return {"job_id": job_id, "status": "todo"}
