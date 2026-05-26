"""FastAPI Dependency 工厂。

约定：
- 所有 endpoint 通过 Depends 获取 db session / current user，禁止直接 import session 实例。
- current_user 在 Phase 0 阶段返回 default_user_id（写死），后期接 JWT 中间件。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
import app.db.postgres as _pg


async def get_db() -> AsyncIterator[AsyncSession]:
    async with _pg.async_session_factory() as session:
        yield session


def get_current_user_id() -> int:
    """临时占位：返回 .env 里 DEFAULT_USER_ID。

    Phase 1+ 加 JWT 后替换为从 token 解析。
    """
    return settings.default_user_id


CurrentUserId = Depends(get_current_user_id)
DB = Depends(get_db)
