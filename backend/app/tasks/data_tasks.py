"""数据下载任务（AKShare → ArcticDB）。Phase 1 实现。"""
from __future__ import annotations

from loguru import logger

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.data_tasks.refresh_symbol_list")
def refresh_symbol_list() -> dict:
    logger.info("[stub] refresh_symbol_list — Phase 1")
    return {"status": "todo"}


@celery_app.task(name="app.tasks.data_tasks.download_daily_kline_all")
def download_daily_kline_all() -> dict:
    logger.info("[stub] download_daily_kline_all — Phase 1")
    return {"status": "todo"}


@celery_app.task(name="app.tasks.data_tasks.download_one_symbol")
def download_one_symbol(symbol: str, period: str = "1d") -> dict:
    logger.info("[stub] download_one_symbol {} {} — Phase 1", symbol, period)
    return {"symbol": symbol, "period": period, "status": "todo"}
