"""模拟交易路由（Phase 4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DB, CurrentUserId
from app.schemas.sim import PositionOut, SimOrderOut
from app.services import sim as sim_svc

router = APIRouter()


@router.get("/orders", response_model=list[SimOrderOut])
async def list_orders(
    strategy_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await sim_svc.list_orders(db, user_id, strategy_id=strategy_id, limit=limit)


@router.get("/position/{symbol}", response_model=PositionOut)
async def get_position(
    symbol: str,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await sim_svc.get_position(db, user_id, symbol)
