"""PostgreSQL 异步连接管理。

引擎 + sessionmaker 都是模块级单例，通过 init_engine() / dispose_engine() 控制生命周期。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None  # type: ignore[assignment]


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def init_engine() -> None:
    global _engine, async_session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    async_session_factory = async_sessionmaker(  # type: ignore[assignment]
        _engine, class_=AsyncSession, expire_on_commit=False
    )


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def get_engine() -> AsyncEngine:
    assert _engine is not None, "engine not initialized; call init_engine() first"
    return _engine
