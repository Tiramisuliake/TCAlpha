"""数据下载任务（AKShare → ArcticDB / PG）。Phase 1 实现。"""
from __future__ import annotations

from datetime import timedelta

from loguru import logger

from app.tasks.celery_app import celery_app
from app.utils.trading_period import now_cn

_DEFAULT_HISTORY_DAYS = 365 * 3  # 默认拉 3 年历史
_MINUTE_PERIOD_MAP = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


def _upsert_sync_log(
    symbol: str,
    period: str,
    status: str,
    last_date: str | None = None,
    rows: int = 0,
    error: str | None = None,
) -> None:
    """记录/更新某只票某周期的同步水位（同步 session，幂等 upsert）。"""
    from sqlalchemy import select

    from app.db.models.sync_log import SyncLog
    from app.db.postgres import SyncSessionLocal
    from app.utils.symbol import normalize

    sym = normalize(symbol)
    try:
        with SyncSessionLocal() as db:
            row = db.execute(
                select(SyncLog).where(SyncLog.symbol == sym, SyncLog.period == period)
            ).scalar_one_or_none()
            if row is None:
                row = SyncLog(symbol=sym, period=period)
                db.add(row)
            row.status = status
            if last_date is not None:
                row.last_date = last_date
            row.rows = rows
            row.error = error
            db.commit()
    except Exception as exc:
        logger.warning("upsert sync_log failed for {} {}: {}", sym, period, exc)


def _last_synced_date(symbol: str, period: str) -> str | None:
    """读上次同步成功的水位日期（增量起点）；无记录/上次失败返回 None。"""
    from sqlalchemy import select

    from app.db.models.sync_log import SyncLog
    from app.db.postgres import SyncSessionLocal
    from app.utils.symbol import normalize

    sym = normalize(symbol)
    try:
        with SyncSessionLocal() as db:
            row = db.execute(
                select(SyncLog).where(SyncLog.symbol == sym, SyncLog.period == period)
            ).scalar_one_or_none()
            return row.last_date if row and row.status == "ok" else None
    except Exception:
        return None


def _send_sync_alert(text: str) -> None:
    """数据同步最终失败 → 飞书系统告警（仅当配置了 sync_alert_webhook）。"""
    from app.config import settings

    if not settings.sync_alert_webhook:
        return
    try:
        import asyncio

        from app.services.feishu import send_text

        ok, err = asyncio.run(
            send_text(settings.sync_alert_webhook, settings.sync_alert_secret, text)
        )
        if not ok:
            logger.warning("sync alert feishu failed: {}", err)
    except Exception as exc:
        logger.warning("sync alert dispatch failed: {}", exc)


@celery_app.task(
    name="app.tasks.data_tasks.refresh_market_snapshot",
    bind=True,
    time_limit=120,
)
def refresh_market_snapshot(self) -> dict:
    """刷新全市场快照（市值/PE/成交额/换手）写 Redis，供选股器筛选。"""
    from app.services.screener import refresh_snapshot_cache_sync

    rows = refresh_snapshot_cache_sync()
    logger.info("refresh_market_snapshot: {} rows cached", rows)
    return {"rows": rows}


@celery_app.task(
    name="app.tasks.data_tasks.refresh_symbol_list",
    bind=True,
    max_retries=3,
)
def refresh_symbol_list(self) -> dict:
    """拉取 AKShare 全市场股票列表，upsert 到 PG symbols 表。"""
    try:
        from sqlalchemy import select

        from app.db.models.symbol import Symbol
        from app.db.postgres import SyncSessionLocal
        from app.services.data import fetch_symbol_list

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
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5) from exc


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
    """下载单个股票 K 线并写入 ArcticDB（增量 + 同步状态记录 + 失败告警）。"""
    try:
        now = now_cn()
        end = end or now.strftime("%Y-%m-%d")
        if start is None:
            # 增量：优先从上次同步水位起（日线）；无水位则拉默认历史
            incr = _last_synced_date(symbol, period) if period == "1d" else None
            start = incr or (now - timedelta(days=_DEFAULT_HISTORY_DAYS)).strftime("%Y-%m-%d")

        if period == "1d":
            from app.services.data import download_and_save_daily
            result = download_and_save_daily(symbol, start, end)
        elif period in _MINUTE_PERIOD_MAP:
            from app.services.data import download_and_save_minute
            # 分钟接口接受 YYYY-MM-DD HH:MM:SS；不传则用 AKShare 默认窗口
            result = download_and_save_minute(
                symbol,
                _MINUTE_PERIOD_MAP[period],
                start if start and " " in start else None,
                end if end and " " in end else None,
            )
        else:
            logger.warning("period {} not yet implemented, skip {}", period, symbol)
            return {"symbol": symbol, "period": period, "status": "skipped"}

        _upsert_sync_log(symbol, period, "ok", last_date=end, rows=int(result.get("rows", 0)))
        logger.info("download_one_symbol done: {}", result)
        return {**result, "status": "ok"}

    except Exception as exc:
        logger.exception("download_one_symbol {} failed: {}", symbol, exc)
        if self.request.retries >= self.max_retries:
            # 最终失败：落库 failed + 飞书告警，不再重试（避免无限占用队列）
            _upsert_sync_log(symbol, period, "failed", error=str(exc)[:500])
            _send_sync_alert(
                f"⚠️ 数据同步失败\n{symbol} [{period}]\n{type(exc).__name__}: {exc}"
            )
            return {"symbol": symbol, "period": period, "status": "failed", "error": str(exc)}
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 3) from exc


@celery_app.task(
    name="app.tasks.data_tasks.download_daily_kline_all",
    bind=True,
)
def download_daily_kline_all(self) -> dict:
    """每日 20:00 beat 触发：为所有活跃股票队列日 K 下载任务。"""
    try:
        from sqlalchemy import select

        from app.db.models.symbol import Symbol
        from app.db.postgres import SyncSessionLocal

        now = now_cn()
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


@celery_app.task(
    name="app.tasks.data_tasks.push_quote_snapshot",
    bind=True,
    max_retries=2,
)
def push_quote_snapshot(self, symbols: list[str] | None = None) -> dict:
    """按 symbol publish 实时报价到 ``quote:<symbol>`` channel。

    - symbols 必传：走 fetch_single_quote 逐个拉（推荐，避开 AKShare 58 页分页）
    - symbols 为空：fallback 走 fetch_spot_snapshot 全市场（best-effort）
    - 非交易时段直接 skip
    """
    try:
        from app.utils.trading_period import is_trading_time

        if not is_trading_time():
            return {"status": "skipped", "reason": "not_trading_time"}

        from app.core.pubsub import publish_quote

        count = 0
        if symbols:
            from app.services.quote import fetch_quotes

            for q in fetch_quotes(symbols):
                publish_quote(q["symbol"], q)
                count += 1
        else:
            from app.services.quote import build_quote_dict, fetch_spot_snapshot

            df = fetch_spot_snapshot()
            for _, row in df.iterrows():
                publish_quote(row["symbol"], build_quote_dict(row))
                count += 1

        logger.info("push_quote_snapshot: pushed {} quotes", count)
        return {"status": "ok", "pushed": count}

    except Exception as exc:
        logger.exception("push_quote_snapshot failed: {}", exc)
        raise self.retry(exc=exc, countdown=10) from exc


@celery_app.task(
    name="app.tasks.data_tasks.download_minute_kline_all",
    bind=True,
)
def download_minute_kline_all(self, period: str = "1m", limit: int | None = None) -> dict:
    """交易时段 beat 触发：为活跃股票队列分钟 K 增量下载。

    - period: 1m/5m/15m/30m/60m
    - limit: 测试用，仅入队前 N 个
    交易时段判断由 ``app.utils.trading_period`` 提供；非交易时段直接 skip。
    """
    try:
        from app.utils.trading_period import is_trading_time

        if not is_trading_time():
            logger.info("download_minute_kline_all: not trading time, skip")
            return {"status": "skipped", "reason": "not_trading_time"}

        if period not in _MINUTE_PERIOD_MAP:
            raise ValueError(f"invalid period: {period}")

        from sqlalchemy import select

        from app.db.models.symbol import Symbol
        from app.db.postgres import SyncSessionLocal

        with SyncSessionLocal() as db:
            stmt = select(Symbol.symbol).where(Symbol.is_active.is_(True))
            if limit:
                stmt = stmt.limit(limit)
            symbols = db.execute(stmt).scalars().all()

        count = 0
        for sym in symbols:
            download_one_symbol.apply_async(
                args=[sym, period],
                countdown=count * 0.6,
            )
            count += 1

        logger.info("download_minute_kline_all[{}]: queued {} tasks", period, count)
        return {"status": "ok", "period": period, "queued": count}

    except Exception as exc:
        logger.exception("download_minute_kline_all failed: {}", exc)
        raise
