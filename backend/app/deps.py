"""FastAPI Dependency 工厂。

约定：
- 所有 endpoint 通过 Depends 获取 db session / current user，禁止直接 import session 实例。

Phase 7 v0.7.0a 软升级：
- get_current_user_id 优先从 Authorization Bearer 解析 access token 的 sub
- 解析失败 / 缺失 → fallback 到 settings.default_user_id（向后兼容 Basic Auth 时期前端）
- v0.7.0b 前端 JWT 切换完成后再硬切：未带 token 直接 401
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
import app.db.postgres as _pg


async def get_db() -> AsyncIterator[AsyncSession]:
    async with _pg.async_session_factory() as session:
        yield session


def get_current_user_id(request: Request) -> int:
    """优先 JWT，缺失或失效则 fallback default_user_id（兼容期）。"""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            # 延迟 import 避免模块循环（security → redis_client → config）
            from app.core.security import TOKEN_TYPE_ACCESS, TokenError, decode_token

            payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
            return int(payload["sub"])
        except (TokenError, ValueError, KeyError, TypeError):
            pass
    return settings.default_user_id


CurrentUserId = Depends(get_current_user_id)
DB = Depends(get_db)
