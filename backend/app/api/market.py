"""行情路由（Phase 1）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_permission
from app.deps import DB
from app.schemas.market import (
    DownloadTriggerResponse,
    KlineResponse,
    LimitUpLadder,
    NorthFlowOut,
    RefreshTriggerResponse,
    TimingSignalOut,
    SentimentOut,
    SentimentPoint,
    SymbolListResponse,
)
from app.schemas.screener import PatternMarker
from app.services import market as market_svc
from app.services import market_sentiment as sentiment_svc

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
    db: AsyncSession = DB,
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


@router.get(
    "/kline/{symbol}/patterns",
    response_model=list[PatternMarker],
    dependencies=[Depends(require_permission("data.read"))],
)
async def kline_patterns(
    symbol: str,
    lookback: int = Query(default=250, ge=20, le=1200),
):
    """该股票历史每日命中的短线形态（K 线图打标，仅日线）。"""
    import asyncio

    from app.services import short_term as short_term_svc

    return await asyncio.to_thread(short_term_svc.pattern_markers, symbol, lookback)


@router.get(
    "/sentiment",
    response_model=SentimentOut,
    dependencies=[Depends(require_permission("data.read"))],
)
async def market_sentiment():
    """市场情绪温度计：实时聚合全市场 spot 快照的涨跌停 / 涨跌比 / 赚钱效应 / 温度。"""
    return await sentiment_svc.get_current_sentiment()


@router.get(
    "/sentiment/history",
    response_model=list[SentimentPoint],
    dependencies=[Depends(require_permission("data.read"))],
)
async def market_sentiment_history(
    days: int = Query(default=120, ge=5, le=500),
):
    """市场情绪历史曲线（每日收盘 beat 存档）。"""
    return await sentiment_svc.get_sentiment_history(days)


@router.get(
    "/limit-up-ladder",
    response_model=LimitUpLadder,
    dependencies=[Depends(require_permission("data.read"))],
)
async def limit_up_ladder():
    """连板梯队：全市场各连板档家数 + 最高板 + 高板龙头（打板情绪高度）。"""
    import asyncio

    return await asyncio.to_thread(sentiment_svc.compute_limit_up_ladder)


@router.get(
    "/north-flow",
    response_model=NorthFlowOut,
    dependencies=[Depends(require_permission("data.read"))],
)
async def north_flow(days: int = Query(default=60, ge=5, le=250)):
    """北向资金当日净流入 + 历史曲线（盘中 beat 更新；接口不可用时 ready=False）。"""
    return await sentiment_svc.get_north_flow(days)


@router.get(
    "/timing-signal",
    response_model=TimingSignalOut,
    dependencies=[Depends(require_permission("data.read"))],
)
async def timing_signal():
    """综合择时信号：温度 + 涨跌停强度 + 北向资金合成仓位建议（全走缓存，毫秒级）。"""
    return await sentiment_svc.get_timing_signal()
