---
name: fastapi-development
description: FastAPI 路由 / Depends / 三层架构 / CORS / 中间件 / SSE。触发词：FastAPI、路由、endpoint、router、Depends、CORS、中间件、API
---

# FastAPI 开发

## 三层架构

```
api/      路由 — 仅做参数校验 + 调 service
services/ 业务逻辑 — 跨 db / cache / 外部 API
db/       数据访问 — ORM + 原生 query
```

**路由不能直接调 ORM**；service 不能 import `Request`。

## 路由模板

```python
# app/api/strategy.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user_id, get_db
from app.schemas.strategy import StrategyCreate, StrategyOut
from app.services import strategy as strategy_svc

router = APIRouter()


@router.get("/list", response_model=list[StrategyOut])
async def list_strategies(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await strategy_svc.list_for_user(db, user_id)


@router.post("/", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    try:
        return await strategy_svc.create(db, user_id, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
```

## main.py 挂载

```python
from app.api import strategy
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
```

## Depends 约定

| Dep | 来源 | 用途 |
|---|---|---|
| `get_db` | `app.deps` | AsyncSession（with 自动关闭） |
| `get_current_user_id` | `app.deps` | 前期返回 `settings.default_user_id`；后期接 JWT |

不要在路由里手动建 session；不要在路由里 import settings 用作业务（settings 给 service / startup 用）。

## CORS

`app/main.py` 已配 `CORSMiddleware`，origins 从 `settings.cors_origins` 读。开发期含 `localhost:5173`。

## 异常处理

```python
# 业务异常 → HTTPException
if not user:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

# 全局兜底（如要）写在 main.py：
@app.exception_handler(SomeBusinessError)
async def biz_handler(req, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
```

## SSE（流式响应）

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

## WebSocket

```python
@router.websocket("/ws/quote")
async def quote_ws(ws: WebSocket):
    await ws.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe("quote:*")
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "pmessage":
                await ws.send_text(msg["data"])
    except WebSocketDisconnect:
        await pubsub.unsubscribe()
```

多 worker 部署时必须 Redis pub/sub，不能用进程内 dict。

## 后台任务（轻量、阻塞型）

```python
from fastapi import BackgroundTasks

@router.post("/notify")
async def notify(bg: BackgroundTasks):
    bg.add_task(send_email, "...")
```

但**耗时 > 2s 一律走 Celery**，不要 BackgroundTasks。

## 性能 / 安全

- 所有外部 API 调用必须设 timeout
- 限流：用 `slowapi` 或 nginx 层
- 防 SQL 注入：永远走 ORM 参数化
- 防 XSS：FastAPI 返回 JSON，前端用 React 自动转义
- 路径参数白名单：`/items/{id:int}` 用 `int` 约束类型

## 禁止

- ❌ 全局 session（`session = SessionLocal()`）
- ❌ endpoint 里 `time.sleep(5)`（用 `asyncio.sleep` 或 Celery）
- ❌ 业务逻辑混进路由
- ❌ `print` 调试（用 `loguru.logger`）
