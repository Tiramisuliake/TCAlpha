"""行情查询业务逻辑（Phase 1）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.arctic import get_library
from app.db.models.symbol import Symbol
from app.schemas.market import KlineBar, KlineResponse, SymbolListResponse, SymbolOut
from app.utils.symbol import normalize

_FALLBACK_DAYS = 365


async def get_symbols(
    db: AsyncSession,
    search: str | None = None,
    exchange: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SymbolListResponse:
    stmt = select(Symbol).where(Symbol.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Symbol.name.ilike(pattern) | Symbol.code.ilike(pattern)
        )
    if exchange:
        stmt = stmt.where(Symbol.exchange == exchange.upper())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Symbol.symbol).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return SymbolListResponse(
        items=[SymbolOut.model_validate(r) for r in rows],
        total=total,
    )


def get_kline(symbol: str, period: str = "1d", limit: int = 200) -> KlineResponse:
    """从 ArcticDB 读取 K 线，返回最新 limit 条。"""
    lib_name = f"bar_{period}"
    sym_key = normalize(symbol)

    try:
        lib = get_library(lib_name)
        if sym_key not in lib.list_symbols():
            logger.info("kline not found in arctic: {} {}", sym_key, period)
            return KlineResponse(symbol=sym_key, period=period, bars=[], total=0)

        df = lib.read(sym_key).data
        df = df.tail(limit)

        bars: list[KlineBar] = []
        for dt, row in df.iterrows():
            bars.append(KlineBar(
                dt=dt.to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                amount=float(row["amount"]) if "amount" in row else None,
            ))
        return KlineResponse(symbol=sym_key, period=period, bars=bars, total=len(bars))

    except Exception as exc:
        logger.error("get_kline error {}: {}", sym_key, exc)
        return KlineResponse(symbol=sym_key, period=period, bars=[], total=0)


def trigger_refresh_symbols() -> str:
    """触发 Celery 刷新全市场股票列表，返回 task_id。"""
    from app.tasks.data_tasks import refresh_symbol_list

    result = refresh_symbol_list.delay()
    return result.id


def trigger_download(symbol: str, period: str = "1d") -> str:
    """触发 Celery 下载任务，返回 task_id。

    分钟级周期使用 AKShare 默认时间窗口（不显式传 start/end），日线传 3 年窗口。
    """
    from app.tasks.data_tasks import download_one_symbol

    if period.endswith("m"):
        result = download_one_symbol.delay(symbol, period)
    else:
        now = datetime.now(tz=UTC)
        end = now.strftime("%Y-%m-%d")
        start = (now - timedelta(days=_FALLBACK_DAYS)).strftime("%Y-%m-%d")
        result = download_one_symbol.delay(symbol, period, start, end)
    return result.id
