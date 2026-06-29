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
        "app.tasks.screen_tasks",
        "app.tasks.sim_tasks",
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
    # 分钟 K 增量：交易时段每 5 分钟（仅 9-11 / 13-14 时段，任务内还会再次校验 is_trading_time）
    "minute-kline-5m-trading": {
        "task": "app.tasks.data_tasks.download_minute_kline_all",
        "schedule": crontab(minute="*/5", hour="9-11,13-14"),
        "kwargs": {"period": "5m"},
    },
    # 1m 节奏更紧：每 2 分钟一次
    "minute-kline-1m-trading": {
        "task": "app.tasks.data_tasks.download_minute_kline_all",
        "schedule": crontab(minute="*/2", hour="9-11,13-14"),
        "kwargs": {"period": "1m"},
    },
    # 实时报价：交易时段每分钟全市场快照推一次
    "push-quote-snapshot-1min": {
        "task": "app.tasks.data_tasks.push_quote_snapshot",
        "schedule": crontab(minute="*", hour="9-11,13-14"),
    },
    # 短线选股：交易日收盘后（15:05）扫描全部 4 形态，汇总一条推送
    "short-term-scan-close": {
        "task": "app.tasks.screen_tasks.scan_multi_pattern_daily",
        "schedule": crontab(hour=15, minute=5, day_of_week="1-5"),
        "kwargs": {"top": 5},
    },
    # 因子快照缓存：交易日收盘后（15:10）刷新全市场因子值，加速多因子选股
    "factor-cache-refresh-close": {
        "task": "app.tasks.screen_tasks.refresh_factor_cache",
        "schedule": crontab(hour=15, minute=10, day_of_week="1-5"),
    },
    # 多因子选股：交易日收盘后（15:12，因子缓存刷新后）综合打分 top10 推送
    "factor-screen-daily-close": {
        "task": "app.tasks.screen_tasks.factor_screen_daily",
        "schedule": crontab(hour=15, minute=12, day_of_week="1-5"),
        "kwargs": {"top": 10},
    },
    # 模拟账户：交易日收盘后（15:30）快照各用户净值，供净值曲线复盘
    "sim-equity-snapshot-close": {
        "task": "app.tasks.sim_tasks.snapshot_all_equity",
        "schedule": crontab(hour=15, minute=30, day_of_week="1-5"),
    },
}
