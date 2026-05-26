"""WebSocket 推送（Phase 4）。

/ws/orders  — 推送当前用户的订单状态变更（订阅 Redis order:user:{uid}）
/ws/signals — 推送策略信号（订阅 Redis signal:strategy:{sid}）
/ws/quote   — 行情推送（订阅 Redis quote 频道）
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.pubsub import order_channel, signal_channel
from app.db.redis_client import get_redis

router = APIRouter()

_HEARTBEAT_INTERVAL = 30


async def _redis_to_ws(ws: WebSocket, channel: str) -> None:
    """把 Redis pub/sub channel 的消息转发给 WebSocket 客户端。"""
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    logger.info("ws subscribed channel={}", channel)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                return

    hb = asyncio.create_task(heartbeat())
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])
    except WebSocketDisconnect:
        logger.info("ws disconnected channel={}", channel)
    except Exception as exc:
        logger.warning("ws error channel={}: {}", channel, exc)
    finally:
        hb.cancel()
        await pubsub.unsubscribe(channel)
        try:
            await pubsub.aclose()
        except Exception:
            pass


@router.websocket("/ws/orders")
async def orders_ws(
    ws: WebSocket,
    user_id: int = Query(default=1, description="用户 ID（Phase 4 暂不鉴权）"),
):
    """订单状态实时推送。"""
    await ws.accept()
    await _redis_to_ws(ws, order_channel(user_id))


@router.websocket("/ws/signals")
async def signals_ws(
    ws: WebSocket,
    strategy_id: int = Query(..., description="策略 ID"),
):
    """策略信号实时推送。"""
    await ws.accept()
    await _redis_to_ws(ws, signal_channel(strategy_id))


@router.websocket("/ws/quote")
async def quote_ws(ws: WebSocket):
    """行情推送（发布端由 AKShare 拉取任务写 Redis quote 频道）。"""
    await ws.accept()
    await _redis_to_ws(ws, "quote")
