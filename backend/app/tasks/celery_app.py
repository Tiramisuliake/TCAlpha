"""Celery 应用实例 + beat 调度。

启动：
  worker: celery -A app.tasks.celery_app worker -l info
  beat  : celery -A app.tasks.celery_app beat -l info
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "tcalpha",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.data_tasks",
        "app.tasks.backtest_tasks",
        "app.tasks.strategy_tasks",
        "app.tasks.ai_tasks",
    ],
)

celery_app.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60 * 24 * 7,  # 7 天
)

# Beat 调度（A 股交易日 20:00 收盘后下载日 K，参考观澜节奏）
celery_app.conf.beat_schedule = {
    "daily-download-kline": {
        "task": "app.tasks.data_tasks.download_daily_kline_all",
        "schedule": crontab(hour=20, minute=0),
    },
    "refresh-symbol-list": {
        "task": "app.tasks.data_tasks.refresh_symbol_list",
        "schedule": crontab(hour=8, minute=30),
    },
    # AI 盯盘：交易时段每 15 分钟（9:30 / 9:45 ... / 14:45）
    "ai-watch-all-15min": {
        "task": "app.tasks.ai_tasks.ai_watch_all",
        "schedule": crontab(minute="*/15", hour="9-14"),
    },
}
