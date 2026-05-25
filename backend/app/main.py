"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import ai, backtest, data, health, market, strategy, ws
from app.config import settings
from app.db.postgres import dispose_engine, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TCAlpha starting up (env={})", settings.env)
    init_engine()
    yield
    await dispose_engine()
    logger.info("TCAlpha shutdown")


app = FastAPI(
    title="TCAlpha API",
    version="0.1.0",
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

# 路由挂载
app.include_router(health.router)
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(ws.router, tags=["ws"])


@app.get("/")
def root():
    return {"name": "TCAlpha API", "version": "0.1.0", "docs": "/docs"}
