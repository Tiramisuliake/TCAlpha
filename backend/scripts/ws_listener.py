"""联调用 WebSocket 客户端：订阅 /ws/orders + /ws/signals 把消息打 stdout。"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def listen(url: str, tag: str) -> None:
    async for ws in websockets.connect(url, ping_interval=20):
        print(f"[{tag}] connected: {url}", flush=True)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = raw
                print(f"[{tag}] {msg}", flush=True)
        except websockets.ConnectionClosed:
            print(f"[{tag}] closed, reconnecting…", flush=True)


async def main(strategy_id: int = 1, user_id: int = 1) -> None:
    await asyncio.gather(
        listen(f"ws://localhost:8000/ws/orders?user_id={user_id}", "ORDER"),
        listen(f"ws://localhost:8000/ws/signals?strategy_id={strategy_id}", "SIGNAL"),
    )


if __name__ == "__main__":
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(main(sid))
