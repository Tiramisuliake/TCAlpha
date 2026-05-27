"""AI 盯盘 Celery 任务（Phase 5 Step 3）。

设计：
- ai_watch_all：beat 触发，遍历所有 user 的 watchlist
- 仅在交易时段触发（额外保险，beat 已限制 9-15 时）
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.db.models.watchlist import Watchlist
from app.db.postgres import SyncSessionLocal
from app.services.ai_watcher import watch_symbol
from app.tasks.celery_app import celery_app
from app.utils.trading_period import is_trading_time


@celery_app.task(
    name="app.tasks.ai_tasks.ai_watch_all",
    bind=True,
    time_limit=600,
    soft_time_limit=540,
)
def ai_watch_all(self, force: bool = False) -> dict:
    """盯盘所有用户的 watchlist。

    Args:
        force: True 时跳过交易时段判断（手动调用 / 调试用）
    """
    if not force and not is_trading_time():
        logger.info("ai_watch_all: not trading time, skip (force=False)")
        return {"status": "skipped", "reason": "not trading time"}

    with SyncSessionLocal() as db:
        rows = db.execute(select(Watchlist)).scalars().all()
        targets = [(r.user_id, r.symbol) for r in rows]

    stats = {"ok": 0, "skipped": 0, "failed": 0, "total": len(targets)}
    for user_id, symbol in targets:
        try:
            alert = watch_symbol(user_id, symbol)
            if alert is None:
                stats["skipped"] += 1
            else:
                stats["ok"] += 1
        except Exception:
            logger.exception("ai_watch_all: user={} symbol={} failed", user_id, symbol)
            stats["failed"] += 1

    logger.info("ai_watch_all done: {}", stats)
    return {"status": "ok", **stats}


@celery_app.task(
    name="app.tasks.ai_tasks.ai_watch_one",
    bind=True,
    time_limit=120,
)
def ai_watch_one(self, user_id: int, symbol: str) -> dict:
    """手动触发：对单个 user+symbol 跑一次盯盘。"""
    alert = watch_symbol(user_id, symbol)
    if alert is None:
        return {"status": "skipped", "user_id": user_id, "symbol": symbol}
    return {
        "status": "ok",
        "alert_id": alert.id,
        "user_id": user_id,
        "symbol": symbol,
        "level": alert.level,
    }
