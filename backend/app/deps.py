"""FastAPI Dependency 工厂。

约定：
- 所有 endpoint 通过 Depends 获取 db session / current user，禁止直接 import session 实例。

Phase 7（已硬切，不再 fallback）：
- get_current_user_id 从 Authorization Bearer 解析 access token 的 sub
- 缺失 / 失效 token 一律 401（fail-closed），不再回落到 default_user_id
- 注：用 CurrentUserId 的端点应同时挂 require_permission 做真正的权限闸门
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.postgres as _pg


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = _pg.async_session_factory
    if factory is None:
        _pg.init_engine()
        factory = _pg.async_session_factory
    assert factory is not None
    async with factory() as session:
        yield session


def get_current_user_id(request: Request) -> int:
    """从 Bearer access token 解析 user_id；缺失 / 失效一律 401（不再 fallback）。"""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[7:].strip()
    try:
        # 延迟 import 避免模块循环（security → redis_client → config）
        from app.core.security import TOKEN_TYPE_ACCESS, TokenError, decode_token

        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
        return int(payload["sub"])
    except (TokenError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


CurrentUserId = Depends(get_current_user_id)
DB = Depends(get_db)
