"""回测管理路由（Phase 3）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_permission
from app.deps import DB, CurrentUserId
from app.schemas.backtest import BacktestStatusOut, BacktestSubmit, BacktestTradeOut
from app.services import backtest as backtest_svc

router = APIRouter()


@router.get(
    "/list",
    response_model=list[BacktestStatusOut],
    dependencies=[Depends(require_permission("backtest.read"))],
)
async def list_backtests(
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await backtest_svc.list_backtests(db, user_id)


@router.post(
    "/submit",
    response_model=BacktestStatusOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("backtest.run"))],
)
async def submit_backtest(
    payload: BacktestSubmit,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await backtest_svc.submit_backtest(db, user_id, payload)


@router.get(
    "/{job_id}",
    response_model=BacktestStatusOut,
    dependencies=[Depends(require_permission("backtest.read"))],
)
async def get_backtest(
    job_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    obj = await backtest_svc.get_backtest_status(db, job_id, user_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest job not found")
    return obj


@router.get(
    "/{job_id}/trades",
    response_model=list[BacktestTradeOut],
    dependencies=[Depends(require_permission("backtest.read"))],
)
async def get_backtest_trades(
    job_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    trades = await backtest_svc.get_trades(db, job_id, user_id)
    if trades is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest job not found")
    return trades
