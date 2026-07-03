"""WebSocket 推送（Phase 4）。

/ws/orders  — 推送当前用户的订单状态变更（订阅 Redis order:user:{uid}）
/ws/signals — 推送策略信号（订阅 Redis signal:strategy:{sid}）
/ws/quote   — 行情推送（订阅 Redis quote 频道）
"""
from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, Query, WebSocket, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import AuthUser, load_auth_user
from app.core.pubsub import order_channel, quote_channel, signal_channel
from app.core.security import TOKEN_TYPE_ACCESS, TokenError, decode_token, is_jti_blacklisted
from app.db.redis_client import get_redis
from app.deps import DB
from app.services import strategy as strategy_svc
from app.utils.symbol import normalize

router = APIRouter()

_HEARTBEAT_INTERVAL = 30


async def _close_policy(ws: WebSocket, reason: str) -> None:
    await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)


async def _auth_ws(ws: WebSocket, db: AsyncSession) -> AuthUser | None:
    """浏览器 WebSocket 不能稳定带 Authorization，使用 wsUrl() 拼的 ?token=。"""
    token = ws.query_params.get("token", "").strip()
    if not token:
        await _close_policy(ws, "missing token")
        return None

    try:
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    except TokenError as exc:
        await _close_policy(ws, f"invalid token: {exc}")
        return None

    jti = payload.get("jti", "")
    if await is_jti_blacklisted(jti):
        await _close_policy(ws, "token revoked")
        return None

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        await _close_policy(ws, "invalid token subject")
        return None

    try:
        return await load_auth_user(db, user_id)
    except Exception as exc:
        logger.warning("ws auth failed: {}", exc)
        await _close_policy(ws, "user not found or inactive")
        return None


async def _redis_to_ws(ws: WebSocket, channel: str) -> None:
    """把 Redis pub/sub channel 的消息转发给 WebSocket 客户端。

    三个协程并发竞争：转发 Redis 消息 / 探测客户端断开 / 心跳；任一结束即全部
    取消并清理订阅。避免客户端静默断开时 pubsub.listen() 永久挂起，导致 Redis
    订阅和 asyncio task 泄漏。
    """
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    logger.info("ws subscribed channel={}", channel)

    async def pump_redis() -> None:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])

    async def watch_disconnect() -> None:
        # 纯推送端点客户端不发消息；receive() 仅用于感知断开（抛 WebSocketDisconnect）
        while True:
            await ws.receive()

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            await ws.send_json({"type": "ping"})

    tasks = [
        asyncio.create_task(coro)
        for coro in (pump_redis(), watch_disconnect(), heartbeat())
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        # 回收所有 task（含被取消的）并吞掉 CancelledError / 断开异常
        await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(Exception):
            await pubsub.unsubscribe(channel)
        with suppress(Exception):
            # redis-py 5.x 推荐 aclose()（close 已弃用）；types-redis stub 落后缺该方法
            await pubsub.aclose()  # type: ignore[attr-defined]
        logger.info("ws closed channel={}", channel)


@router.websocket("/ws/orders")
async def orders_ws(
    ws: WebSocket,
    db: AsyncSession = DB,
):
    """订单状态实时推送。"""
    user = await _auth_ws(ws, db)
    if user is None:
        return
    await ws.accept()
    await _redis_to_ws(ws, order_channel(user.id))


@router.websocket("/ws/signals")
async def signals_ws(
    ws: WebSocket,
    strategy_id: int = Query(..., description="策略 ID"),
    db: AsyncSession = DB,
):
    """策略信号实时推送。"""
    user = await _auth_ws(ws, db)
    if user is None:
        return
    if not await strategy_svc.can_subscribe_signals(
        db, strategy_id, user.id, is_super=user.is_super
    ):
        await _close_policy(ws, "strategy not found or forbidden")
        return
    await ws.accept()
    await _redis_to_ws(ws, signal_channel(strategy_id))


@router.websocket("/ws/quote")
async def quote_ws(
    ws: WebSocket,
    symbol: str = Query(..., description="股票代码，如 sh600000 或 600000"),
    db: AsyncSession = DB,
):
    """单 symbol 实时报价 WS（按需订阅 Redis quote:<symbol>）。"""
    user = await _auth_ws(ws, db)
    if user is None:
        return
    if not user.has_permission("data.read"):
        await _close_policy(ws, "missing permission: data.read")
        return
    await ws.accept()
    try:
        sym = normalize(symbol)
    except ValueError as exc:
        await ws.send_json({"type": "error", "message": str(exc)})
        await ws.close(code=1003)
        return
    await _redis_to_ws(ws, quote_channel(sym))
