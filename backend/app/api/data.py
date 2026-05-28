"""数据管理路由（Phase 0 占位）。"""
from fastapi import APIRouter, Depends

from app.core.auth_deps import require_permission

router = APIRouter()


@router.post(
    "/download",
    dependencies=[Depends(require_permission("data.download"))],
)
async def download_data(symbol: str, period: str = "1d"):
    """触发 Celery 任务下载历史数据。"""
    return {"symbol": symbol, "period": period, "task_id": None, "todo": "Phase 1"}
