---
name: websocket-sse
description: WebSocket 实时行情推送 + SSE 流式 AI 回复 / 重连 / 心跳 / 多 worker 广播。触发词：WebSocket、WS、SSE、流式、实时推送、行情、心跳、重连、EventSource
---

# WebSocket & SSE

## 何时用哪个

| 场景 | 选 |
|---|---|
| 行情实时推送（双向、二进制） | **WebSocket** |
| AI 流式输出（单向、文本） | **SSE**（更简单，自动重连） |
| 单次大文件下载 | 普通 HTTP + Range |

## 后端 — WebSocket 模板

```python
# app/api/ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from loguru import logger

from app.db.redis_client import get_redis

router = APIRouter()


@router.websocket("/ws/quote")
async def quote_ws(ws: WebSocket):
    await ws.accept()
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("quote")

    async def heartbeat():
        while True:
            await asyncio.sleep(30)
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
        logger.info("ws client gone")
    finally:
        hb.cancel()
        await pubsub.unsubscribe()
        await pubsub.aclose()
```

**多 worker 必须走 Redis pub/sub**；进程内 dict 只能单 worker。

## 后端 — SSE 模板（AI 流式）

```python
from sse_starlette.sse import EventSourceResponse

@router.get("/chat")
async def chat(message: str):
    async def gen():
        async for chunk in ai_svc.stream(message):
            yield {"data": chunk}
        yield {"data": "[DONE]"}
    return EventSourceResponse(gen())
```

SSE 浏览器自带 `EventSource` API + 自动重连。

## 前端 — 自定义 useWebSocket hook

```ts
// src/hooks/useWebSocket.ts
import { useEffect, useRef } from "react";

export function useWebSocket(
  url: string,
  onMessage: (data: string) => void,
  opts: { reconnectMs?: number } = {}
) {
  const wsRef = useRef<WebSocket | null>(null);
  const closedRef = useRef(false);

  useEffect(() => {
    closedRef.current = false;

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e) => onMessage(e.data);
      ws.onclose = () => {
        if (!closedRef.current) {
          setTimeout(connect, opts.reconnectMs ?? 3000);
        }
      };
      ws.onerror = (e) => {
        console.warn("ws error", e);
        ws.close();
      };
    };
    connect();

    return () => {
      closedRef.current = true;
      wsRef.current?.close();
    };
  }, [url, onMessage, opts.reconnectMs]);

  return wsRef;
}
```

用法：

```tsx
useWebSocket("/ws/quote", (raw) => {
  const tick = JSON.parse(raw);
  qc.setQueryData(["quote", tick.symbol], tick);
});
```

## 前端 — 自定义 useSSE hook

```ts
// src/hooks/useSSE.ts
import { useEffect } from "react";

export function useSSE(url: string, onMessage: (data: string) => void) {
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (e) => {
      if (e.data === "[DONE]") es.close();
      else onMessage(e.data);
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [url, onMessage]);
}
```

## Nginx 代理注意（生产）

```nginx
location /ws/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "Upgrade";
    proxy_read_timeout 86400s;   # 大！否则空闲断
}

location /api/ai/chat {        # SSE
    proxy_pass http://backend;
    proxy_buffering off;        # 必须关
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

## Redis pub/sub 广播（后端发布）

```python
# Celery worker 收到新 tick 后
import json
from app.db.redis_client import get_redis

await get_redis().publish("quote", json.dumps({"symbol": s, "price": p, "ts": ts}))
```

## 禁止

- ❌ WS 不带心跳（运营商可能 60s 切断）
- ❌ WS 关闭后无限快速重连（要指数退避或固定间隔）
- ❌ SSE 服务端忘了 `proxy_buffering off`（前端看不到流）
- ❌ 多 worker 用单进程内 dict 做广播
- ❌ 把鉴权 token 放 URL query（用 cookie 或 header）
