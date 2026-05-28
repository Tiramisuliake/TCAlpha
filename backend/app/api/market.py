"""行情路由（Phase 1）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_permission
from app.deps import get_db
from app.schemas.market import (
    DownloadTriggerResponse,
    KlineResponse,
    RefreshTriggerResponse,
    SymbolListResponse,
)
from app.services import market as market_svc

router = APIRouter()


@router.post(
    "/symbols/refresh",
    response_model=RefreshTriggerResponse,
    dependencies=[Depends(require_permission("data.download"))],
)
async def refresh_symbols():
    """触发 Celery 刷新全市场股票列表（异步，立即返回 task_id）。"""
    task_id = market_svc.trigger_refresh_symbols()
    return RefreshTriggerResponse(task_id=task_id)


@router.get(
    "/symbols",
    response_model=SymbolListResponse,
    dependencies=[Depends(require_permission("data.read"))],
)
async def list_symbols(
    search: str | None = Query(default=None, description="按代码或名称模糊搜索"),
    exchange: str | None = Query(default=None, description="交易所过滤：SH / SZ / BJ"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取股票列表（分页 + 搜索）。"""
    return await market_svc.get_symbols(db, search=search, exchange=exchange, limit=limit, offset=offset)


@router.get(
    "/kline/{symbol}",
    response_model=KlineResponse,
    dependencies=[Depends(require_permission("data.read"))],
)
async def get_kline(
    symbol: str,
    period: str = Query(default="1d", description="K线周期：1d / 1m / 5m / 15m / 30m / 60m"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    """获取 K 线数据（从 ArcticDB 读取）。"""
    if period not in {"1d", "1m", "5m", "15m", "30m", "60m"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported period: {period}")
    return market_svc.get_kline(symbol, period=period, limit=limit)


@router.post(
    "/kline/{symbol}/download",
    response_model=DownloadTriggerResponse,
    dependencies=[Depends(require_permission("data.download"))],
)
async def trigger_download(
    symbol: str,
    period: str = Query(default="1d"),
):
    """触发 Celery 下载该股票 K 线（异步，立即返回 task_id）。"""
    task_id = market_svc.trigger_download(symbol, period=period)
    return DownloadTriggerResponse(symbol=symbol, task_id=task_id)
