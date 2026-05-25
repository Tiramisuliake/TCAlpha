"""WebSocket 行情推送（Phase 0 占位 echo）。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter()


@router.websocket("/ws/quote")
async def quote_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_json({"echo": msg, "todo": "Phase 2 Redis pub/sub"})
    except WebSocketDisconnect:
        logger.info("ws client disconnected")
