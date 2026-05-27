"""Redis pub/sub channel 名称约定 + 同步发布工具（Celery 内使用）。"""
from __future__ import annotations

import json

import redis as _sync_redis

from app.config import settings

_sync_client: _sync_redis.Redis | None = None


def get_sync_redis() -> _sync_redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = _sync_redis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    return _sync_client


# ── Channel 名称 ──────────────────────────────────────────────────────

def order_channel(user_id: int) -> str:
    return f"order:user:{user_id}"


def signal_channel(strategy_id: int) -> str:
    return f"signal:strategy:{strategy_id}"


def quote_channel(symbol: str) -> str:
    """单 symbol 实时报价 channel。"""
    return f"quote:{symbol.lower()}"


def stop_key(strategy_id: int) -> str:
    """Redis key：若存在表示该策略应停止。"""
    return f"strategy:stop:{strategy_id}"


def running_key(strategy_id: int) -> str:
    """Redis key：value = celery task_id，表示运行中。"""
    return f"strategy:running:{strategy_id}"


# ── 同步发布（Celery worker 调）────────────────────────────────────────

def publish_order(user_id: int, order_dict: dict) -> None:
    get_sync_redis().publish(order_channel(user_id), json.dumps(order_dict))


def publish_signal(strategy_id: int, signal_dict: dict) -> None:
    get_sync_redis().publish(signal_channel(strategy_id), json.dumps(signal_dict))


def publish_quote(symbol: str, quote_dict: dict) -> None:
    """实时报价发布（Celery 拉 AKShare 后调用）。"""
    get_sync_redis().publish(quote_channel(symbol), json.dumps(quote_dict))
