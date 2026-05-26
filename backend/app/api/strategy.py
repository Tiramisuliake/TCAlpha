"""策略管理路由（Phase 3+4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DB, CurrentUserId
from app.schemas.strategy import StrategyCreate, StrategyOut
from app.services import sim as sim_svc
from app.services import strategy as strategy_svc

router = APIRouter()


@router.get("/classes")
async def list_strategy_classes():
    """已注册的策略类（如 MaCrossStrategy）。"""
    return {"classes": strategy_svc.get_strategy_classes()}


@router.get("/list", response_model=list[StrategyOut])
async def list_strategies(
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await strategy_svc.list_strategies(db, user_id)


@router.post("", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await strategy_svc.create_strategy(db, user_id, payload)


@router.put("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(
    strategy_id: int,
    payload: StrategyCreate,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    obj = await strategy_svc.update_strategy(db, strategy_id, user_id, payload)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    return obj


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    ok = await strategy_svc.delete_strategy(db, strategy_id, user_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")


@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """启动策略 Celery worker（长跑任务）。"""
    result = await sim_svc.start_strategy(db, strategy_id, user_id)
    if "error" in result:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    return result


@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """设置 Redis stop 标志，通知策略 worker 退出。"""
    result = await sim_svc.stop_strategy(db, strategy_id, user_id)
    if "error" in result:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    return result


@router.get("/{strategy_id}/running")
async def strategy_running(strategy_id: int, _: int = CurrentUserId):
    """查询策略是否在运行（检查 Redis running key）。"""
    return {"strategy_id": strategy_id, "running": sim_svc.get_strategy_running_status(strategy_id)}
