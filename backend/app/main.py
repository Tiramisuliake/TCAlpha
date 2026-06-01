"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from loguru import logger

from app import __version__
from app.api import (
    ai,
    ai_alerts,
    ai_chart,
    auth,
    backtest,
    data,
    health,
    market,
    notify,
    sim,
    strategy,
    system,
    watchlist,
    ws,
)
from app.config import settings
from app.core.event_bus import publish_event
from app.db.postgres import dispose_engine, init_engine
from app.middleware.basic_auth import BasicAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TCAlpha starting up (env={})", settings.env)
    init_engine()
    yield
    await dispose_engine()
    logger.info("TCAlpha shutdown")


app = FastAPI(
    title="TCAlpha API",
    version=__version__,
    description="A 股量化分析、回测与模拟交易后端",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic Auth（按 settings.auth_enabled 开关；放在 CORS 之后让预检 OPTIONS 不被拦）
if settings.auth_enabled:
    if not settings.auth_password_hash:
        logger.warning(
            "AUTH_ENABLED=true 但 AUTH_PASSWORD_HASH 为空，所有请求将被拒绝。"
            " 请用 scripts/gen_password_hash.py 生成密码哈希。"
        )
    app.add_middleware(
        BasicAuthMiddleware,
        username=settings.auth_username,
        password_hash=settings.auth_password_hash,
        public_paths=settings.auth_public_paths_list,
        protect_docs=settings.auth_protect_docs,
    )
    logger.info(
        "BasicAuth enabled: user={} public_paths={} protect_docs={}",
        settings.auth_username,
        settings.auth_public_paths_list,
        settings.auth_protect_docs,
    )

# 路由挂载
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(ai_chart.router, prefix="/api/ai/chart", tags=["ai-chart"])
app.include_router(sim.router, prefix="/api/sim", tags=["sim"])
app.include_router(notify.router, prefix="/api/notify", tags=["notify"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"])
app.include_router(ai_alerts.router, prefix="/api/ai-alerts", tags=["ai-alerts"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(ws.router, tags=["ws"])


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled API exception: {} {}", request.method, request.url.path)
    publish_event(
        "api.exception",
        {
            "method": request.method,
            "path": request.url.path,
            "exception": type(exc).__name__,
            "detail": str(exc)[:300],
        },
        level="danger",
    )
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "detail": "服务器内部错误"},
    )


@app.get("/")
def root():
    return {"name": "TCAlpha API", "version": __version__, "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
