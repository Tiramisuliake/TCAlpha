"""数据管理路由。"""
import asyncio

from fastapi import APIRouter, Depends

from app.core.auth_deps import require_permission
from app.schemas.data import DataHealthOut
from app.services import data as data_svc

router = APIRouter()


@router.post(
    "/download",
    dependencies=[Depends(require_permission("data.download"))],
)
async def download_data(symbol: str, period: str = "1d"):
    """触发 Celery 任务下载历史数据。"""
    return {"symbol": symbol, "period": period, "task_id": None, "todo": "Phase 1"}


@router.get(
    "/health",
    response_model=DataHealthOut,
    dependencies=[Depends(require_permission("data.read"))],
)
async def data_health():
    """数据健康面板：K 线覆盖度 + 同步状态 + 最近失败（选股 / 回测的数据底座）。"""
    return await asyncio.to_thread(data_svc.data_health_sync)
