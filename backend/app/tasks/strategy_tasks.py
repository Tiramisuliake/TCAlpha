"""实时策略 worker（长跑 Celery 任务）。"""
from __future__ import annotations

from loguru import logger

from app.tasks.celery_app import celery_app


@celery_app.task(
    name="app.tasks.strategy_tasks.run_strategy",
    bind=True,
    time_limit=86400,      # 最长 24h
    soft_time_limit=85000,
)
def run_strategy(self, strategy_id: int) -> dict:
    """长跑任务：加载策略 → 热身 → 实时驱动 on_bar → SimGateway 下单。"""
    logger.info("run_strategy start: id={} celery_task={}", strategy_id, self.request.id)
    from app.core.runtime import StrategyRuntime

    runtime = StrategyRuntime(strategy_id)
    return runtime.run(celery_task_id=self.request.id)
