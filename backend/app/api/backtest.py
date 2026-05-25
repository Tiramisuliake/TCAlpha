"""回测管理路由（Phase 0 占位）。"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/submit")
async def submit_backtest():
    return {"job_id": None, "todo": "Phase 3"}


@router.get("/{job_id}")
async def get_backtest(job_id: int):
    return {"job_id": job_id, "status": "todo", "todo": "Phase 3"}
