"""模拟交易路由（Phase 4 + 手工下单扩展）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import CurrentUser, effective_scope, require_permission
from app.deps import DB, CurrentUserId
from app.schemas.sim import (
    AccountOut,
    EquityCurveOut,
    PlaceOrderRequest,
    PositionOut,
    PositionSummary,
    SimOrderOut,
)
from app.services import sim as sim_svc

router = APIRouter()


@router.get(
    "/orders",
    response_model=list[SimOrderOut],
    dependencies=[Depends(require_permission("sim.order.read"))],
)
async def list_orders(
    user: CurrentUser,
    strategy_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = DB,
):
    return await sim_svc.list_orders(
        db, user.id, strategy_id=strategy_id, limit=limit, scope=effective_scope(user)
    )


@router.post(
    "/orders",
    response_model=SimOrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("sim.order.place"))],
)
async def place_order(
    payload: PlaceOrderRequest,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """手工市价单：拿当前实时报价立即成交。"""
    try:
        return await sim_svc.place_market_order(
            db, user_id,
            symbol=payload.symbol,
            direction=payload.direction,
            offset=payload.offset,
            volume=payload.volume,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post(
    "/orders/{order_id}/cancel",
    response_model=SimOrderOut,
    dependencies=[Depends(require_permission("sim.order.cancel"))],
)
async def cancel_order(
    order_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """撤单（仅 submitted 状态有效；已成交 / 已撤幂等返回当前状态）。"""
    res = await sim_svc.cancel_order(db, user_id, order_id)
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    return res


@router.get(
    "/account",
    response_model=AccountOut,
    dependencies=[Depends(require_permission("sim.order.read"))],
)
async def get_account(
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """资金账户快照：现金 / 持仓成本 / 总资产（成本口径）。"""
    return await sim_svc.get_account(db, user_id)


@router.post(
    "/account/reset",
    response_model=AccountOut,
    dependencies=[Depends(require_permission("sim.order.place"))],
)
async def reset_account(
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """重置账户现金到初始资金（订单流水保留）。"""
    return await sim_svc.reset_account(db, user_id)


@router.get(
    "/equity-curve",
    response_model=EquityCurveOut,
    dependencies=[Depends(require_permission("sim.order.read"))],
)
async def equity_curve(
    days: int = Query(default=180, ge=7, le=1000),
    benchmark: str | None = Query(default="000300"),
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """账户每日净值曲线（市值口径，收盘后 beat 记录）+ 可选指数基准对比。"""
    return await sim_svc.get_equity_curve(db, user_id, days=days, benchmark=benchmark)


@router.get(
    "/positions",
    response_model=list[PositionSummary],
    dependencies=[Depends(require_permission("sim.order.read"))],
)
async def list_positions(
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    """汇总当前用户所有非零持仓。"""
    return await sim_svc.list_positions(db, user_id)


@router.get(
    "/position/{symbol}",
    response_model=PositionOut,
    dependencies=[Depends(require_permission("sim.order.read"))],
)
async def get_position(
    symbol: str,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    return await sim_svc.get_position(db, user_id, symbol)
