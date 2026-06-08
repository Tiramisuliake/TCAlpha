"""关注列表 API（Phase 5 Step 3）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_permission
from app.deps import DB, CurrentUserId
from app.schemas.watchlist import BoardOut, WatchlistCreate, WatchlistOut
from app.services import watchlist as watchlist_svc

router = APIRouter()


@router.get(
    "",
    response_model=list[WatchlistOut],
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def list_items(user_id: int = CurrentUserId, db: AsyncSession = DB):
    return await watchlist_svc.list_items(db, user_id)


@router.get(
    "/board",
    response_model=BoardOut,
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def get_board(user_id: int = CurrentUserId, db: AsyncSession = DB):
    """盯盘驾驶舱聚合：自选股 + 报价快照 + 最近 AI 告警。"""
    return await watchlist_svc.get_board(db, user_id)


@router.post(
    "",
    response_model=WatchlistOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def add_item(
    payload: WatchlistCreate,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    obj = await watchlist_svc.add_item(db, user_id, payload)
    if obj is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"已关注 {payload.symbol}"
        )
    return obj


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("ai.watch"))],
)
async def remove_item(
    item_id: int,
    user_id: int = CurrentUserId,
    db: AsyncSession = DB,
):
    ok = await watchlist_svc.remove_item(db, user_id, item_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watchlist item not found")
