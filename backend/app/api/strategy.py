"""策略管理路由（Phase 0 占位）。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/list")
async def list_strategies():
    return {"items": [], "total": 0, "todo": "Phase 3"}


@router.get("/classes")
async def list_strategy_classes():
    """已注册的策略类（如 MaCrossStrategy / MacdStrategy）。"""
    return {"classes": [], "todo": "Phase 3"}
