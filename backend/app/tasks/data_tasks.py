"""数据下载任务（AKShare → ArcticDB / PG）。Phase 1 实现。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger

from app.tasks.celery_app import celery_app

_DEFAULT_HISTORY_DAYS = 365 * 3  # 默认拉 3 年历史


@celery_app.task(
    name="app.tasks.data_tasks.refresh_symbol_list",
    bind=True,
    max_retries=3,
)
def refresh_symbol_list(self) -> dict:
    """拉取 AKShare 全市场股票列表，upsert 到 PG symbols 表。"""
    try:
        from app.services.data import fetch_symbol_list
        from app.db.postgres import SyncSessionLocal
        from app.db.models.symbol import Symbol
        from sqlalchemy import select

        symbols = fetch_symbol_list()
        with SyncSessionLocal() as db:
            for s in symbols:
                existing = db.execute(
                    select(Symbol).where(Symbol.symbol == s["symbol"])
                ).scalar_one_or_none()
                if existing:
                    existing.name = s["name"]
                    existing.exchange = s["exchange"]
                    existing.is_active = True
                else:
                    db.add(Symbol(**s))
            db.commit()

        logger.info("refresh_symbol_list: upserted {} symbols", len(symbols))
        return {"status": "ok", "count": len(symbols)}

    except Exception as exc:
        logger.exception("refresh_symbol_list failed: {}", exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)


@celery_app.task(
    name="app.tasks.data_tasks.download_one_symbol",
    bind=True,
    max_retries=3,
)
def download_one_symbol(
    self,
    symbol: str,
    period: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """下载单个股票 K 线并写入 ArcticDB。"""
    try:
        now = datetime.now(tz=timezone.utc)
        end = end or now.strftime("%Y-%m-%d")
        start = start or (now - timedelta(days=_DEFAULT_HISTORY_DAYS)).strftime("%Y-%m-%d")

        if period == "1d":
            from app.services.data import download_and_save_daily
            result = download_and_save_daily(symbol, start, end)
        else:
            logger.warning("period {} not yet implemented, skip {}", period, symbol)
            return {"symbol": symbol, "period": period, "status": "skipped"}

        logger.info("download_one_symbol done: {}", result)
        return {**result, "status": "ok"}

    except Exception as exc:
        logger.exception("download_one_symbol {} failed: {}", symbol, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 3)


@celery_app.task(
    name="app.tasks.data_tasks.download_daily_kline_all",
    bind=True,
)
def download_daily_kline_all(self) -> dict:
    """每日 20:00 beat 触发：为所有活跃股票队列日 K 下载任务。"""
    try:
        from app.db.postgres import SyncSessionLocal
        from app.db.models.symbol import Symbol
        from sqlalchemy import select

        now = datetime.now(tz=timezone.utc)
        end = now.strftime("%Y-%m-%d")
        start = (now - timedelta(days=5)).strftime("%Y-%m-%d")  # 仅补近 5 天

        with SyncSessionLocal() as db:
            symbols = db.execute(
                select(Symbol.symbol).where(Symbol.is_active.is_(True))
            ).scalars().all()

        count = 0
        for sym in symbols:
            download_one_symbol.apply_async(
                args=[sym, "1d", start, end],
                countdown=count * 0.6,  # 限流：每 0.6s 一个
            )
            count += 1

        logger.info("download_daily_kline_all: queued {} tasks", count)
        return {"status": "ok", "queued": count}

    except Exception as exc:
        logger.exception("download_daily_kline_all failed: {}", exc)
        raise
