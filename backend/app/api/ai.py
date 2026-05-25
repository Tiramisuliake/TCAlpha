"""AI 助手路由（SSE 流式，Phase 0 占位）。"""
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/chat")
async def chat(message: str):
    async def event_gen():
        yield {"data": f"echo: {message}"}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_gen())
