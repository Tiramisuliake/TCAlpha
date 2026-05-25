"""行情查询路由（Phase 0 占位，Phase 1 接 AKShare + ArcticDB）。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/symbols")
async def list_symbols():
    """股票列表（占位）。"""
    return {"items": [], "total": 0, "todo": "Phase 1"}


@router.get("/kline")
async def get_kline(symbol: str, period: str = "1d", limit: int = 200):
    """K 线数据（占位）。"""
    return {"symbol": symbol, "period": period, "limit": limit, "data": [], "todo": "Phase 1"}
