"""多 worker WebSocket pub/sub 广播验证脚本（B6）。

用途：在公网部署 / 多 worker 配置前，验证不同 uvicorn 进程都能通过
Redis pub/sub 收到广播。

前置：
1. 先起两个后端进程在不同端口：
     uv --directory backend run uvicorn app.main:app --port 8000
     uv --directory backend run uvicorn app.main:app --port 8001
2. 两个进程都连同一个 Redis（默认 settings.redis_url）。

跑法（在 backend 目录）：
    uv run python scripts/check_pubsub.py [--user-id 1] [--count 5]

期望输出：每条 publish 的消息在 :8000 和 :8001 端口的 WS client 各收到一份。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import websockets

from app.core.pubsub import order_channel, publish_order


async def listen(url: str, tag: str, bucket: list[dict]) -> None:
    """连一个 WS endpoint，收到的消息追加到 bucket。"""
    try:
        async with websockets.connect(url, ping_interval=20) as ws:
            print(f"[{tag}] connected: {url}", flush=True)
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = {"raw": raw}
                bucket.append(msg)
                print(f"[{tag}] received: {msg}", flush=True)
    except Exception as exc:
        print(f"[{tag}] connection error: {exc}", flush=True)


async def main(user_id: int, count: int, ports: list[int]) -> int:
    buckets: dict[int, list[dict]] = {p: [] for p in ports}
    tasks = [
        asyncio.create_task(
            listen(f"ws://localhost:{p}/ws/orders?user_id={user_id}", f":{p}", buckets[p])
        )
        for p in ports
    ]

    # 给 WS 一点时间订阅
    await asyncio.sleep(1.5)

    # 通过 Redis 发 N 条消息
    print(f"\n→ publishing {count} messages on channel {order_channel(user_id)}\n",
          flush=True)
    for i in range(count):
        publish_order(
            user_id,
            {
                "id": 10000 + i,
                "symbol": "sh600000",
                "direction": "long",
                "offset": "open",
                "price": 10.0 + i * 0.01,
                "volume": 100,
                "status": "submitted",
                "_test_seq": i,
            },
        )
        await asyncio.sleep(0.2)

    # 等收齐
    await asyncio.sleep(2.0)
    for t in tasks:
        t.cancel()

    # 校验
    ok = True
    print("\n── 结果 ────────────────────────────────────────────────", flush=True)
    for p, msgs in buckets.items():
        received = [m for m in msgs if "_test_seq" in m]
        seqs = sorted(m["_test_seq"] for m in received)
        expected = list(range(count))
        match = seqs == expected
        ok = ok and match
        print(f"  port {p}: 收到 {len(received)}/{count} 条 {seqs} → "
              f"{'OK' if match else 'FAIL'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--user-id", type=int, default=1)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--ports", nargs="+", type=int, default=[8000, 8001])
    args = p.parse_args()

    print(f"checking pub/sub broadcast across ports {args.ports} ...", flush=True)
    print(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    rc = asyncio.run(main(args.user_id, args.count, args.ports))
    sys.exit(rc)
