"""AKShare 数据下载 + ArcticDB 落库（Phase 1）。"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.db.arctic import get_library
from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
from app.utils.rate_limit import acquire, wait_for_akshare
from app.utils.symbol import normalize
from app.utils.trading_period import now_cn


def wait_for_rate_limit(max_per_sec: int | None = None) -> None:
    """向后兼容封装：转发到 utils.rate_limit。"""
    if max_per_sec is not None:
        acquire("ak", max_per_sec)
    else:
        wait_for_akshare()


# ──────────────────────────────────────────────
# 股票列表
# ──────────────────────────────────────────────

def fetch_symbol_list() -> list[dict]:
    """全市场股票列表 —— 委托统一 DataProvider。"""
    from app.data import get_provider

    return get_provider().fetch_symbol_list()


# ──────────────────────────────────────────────
# 日 K 线
# ──────────────────────────────────────────────

def fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    """日 K（前复权）—— 委托统一 DataProvider。"""
    from app.data import get_provider

    return get_provider().fetch_daily(symbol, start, end)


def save_daily(symbol: str, df: pd.DataFrame) -> int:
    """增量写入 ArcticDB bar_1d library，返回写入行数。"""
    lib = get_library("bar_1d")
    sym_key = normalize(symbol)

    if sym_key in lib.list_symbols():
        existing: pd.DataFrame = lib.read(sym_key).data
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = df

    lib.write(
        sym_key,
        combined,
        metadata={"source": "akshare", "fetched_at": now_cn().isoformat()},
    )
    rows = len(combined)
    logger.info("save_daily: {} → {} rows total", sym_key, rows)
    return rows


def download_and_save_daily(symbol: str, start: str, end: str) -> dict:
    """下载并落库，返回摘要 dict（供 Celery 任务直接调用）。"""
    df = fetch_daily(symbol, start, end)
    rows = save_daily(symbol, df)
    return {"symbol": normalize(symbol), "rows": rows, "start": start, "end": end}


# ──────────────────────────────────────────────
# 分钟 K 线（Phase 5 C 阶段）
# ──────────────────────────────────────────────

_MINUTE_PERIODS = (1, 5, 15, 30, 60)


def fetch_minute_kline(
    symbol: str,
    period: int,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """分钟 K（前复权），period ∈ {1,5,15,30,60} —— 委托统一 DataProvider。"""
    from app.data import get_provider

    return get_provider().fetch_minute_kline(symbol, period, start, end)


def save_minute(symbol: str, period: int, df: pd.DataFrame) -> int:
    """增量写入 ArcticDB ``bar_{period}m`` library，返回总行数。"""
    if period not in _MINUTE_PERIODS:
        raise ValueError(f"unsupported minute period: {period}")

    lib = get_library(f"bar_{period}m")
    sym_key = normalize(symbol)

    if sym_key in lib.list_symbols():
        existing: pd.DataFrame = lib.read(sym_key).data
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = df

    lib.write(
        sym_key,
        combined,
        metadata={
            "source": "akshare",
            "period": f"{period}m",
            "fetched_at": now_cn().isoformat(),
        },
    )
    rows = len(combined)
    logger.info("save_minute: {} [{}m] → {} rows total", sym_key, period, rows)
    return rows


def download_and_save_minute(
    symbol: str,
    period: int,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """下载并落库分钟 K，返回摘要 dict（供 Celery 任务直接调用）。"""
    df = fetch_minute_kline(symbol, period, start, end)
    rows = save_minute(symbol, period, df)
    return {
        "symbol": normalize(symbol),
        "period": f"{period}m",
        "rows": rows,
        "start": start,
        "end": end,
    }


# ── 数据健康面板（v0.8.21）────────────────────────────────────────────────


def data_health_sync() -> dict:
    """数据健康聚合（同步，供 API to_thread 调用）。

    PG symbols 总数 + ArcticDB bar_1d 实际覆盖数 + 覆盖率 + SyncLog 同步状态计数
    + 最近失败 top10。让用户一眼看出数据完整性（选股 / 回测都依赖它）。
    """
    from sqlalchemy import func, select

    from app.db.models.symbol import Symbol
    from app.db.models.sync_log import SyncLog
    from app.db.postgres import SyncSessionLocal

    with SyncSessionLocal() as db:
        symbols_total = db.scalar(
            select(func.count()).select_from(Symbol).where(Symbol.is_active.is_(True))
        ) or 0
        sync_ok = db.scalar(
            select(func.count()).select_from(SyncLog).where(SyncLog.status == "ok")
        ) or 0
        sync_failed = db.scalar(
            select(func.count()).select_from(SyncLog).where(SyncLog.status == "failed")
        ) or 0
        failures = db.execute(
            select(SyncLog)
            .where(SyncLog.status == "failed")
            .order_by(SyncLog.updated_at.desc())
            .limit(10)
        ).scalars().all()
        recent_failures = [
            {
                "symbol": r.symbol,
                "period": r.period,
                "error": (r.error or "")[:200],
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in failures
        ]

    try:
        # 经 app.db.arctic 模块属性访问，便于测试 monkeypatch get_library 生效
        from app.db import arctic

        bar1d_covered = len(arctic.get_library("bar_1d").list_symbols())
    except Exception:
        bar1d_covered = 0

    coverage_rate = round(bar1d_covered / symbols_total, 4) if symbols_total > 0 else 0.0
    return {
        "symbols_total": int(symbols_total),
        "bar1d_covered": int(bar1d_covered),
        "coverage_rate": coverage_rate,
        "sync_ok": int(sync_ok),
        "sync_failed": int(sync_failed),
        "recent_failures": recent_failures,
    }
