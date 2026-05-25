"""实时策略 worker（长跑任务）。Phase 4 实现。"""
from __future__ import annotations

from loguru import logger

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.strategy_tasks.run_strategy", bind=True)
def run_strategy(self, strategy_id: int) -> dict:
    logger.info("[stub] run_strategy id={} — Phase 4", strategy_id)
    return {"strategy_id": strategy_id, "status": "todo"}
