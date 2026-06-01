"""统一事件总线（Phase 5 Step 1）。

业务点不直接调飞书/邮件/WS，而是 publish_event(type, payload)；
notify_dispatcher worker 订阅 'events:*' 通配，按 NotifyRule 路由到具体渠道。

事件 type 命名约定（dot.case，三层）：
  - strategy.started / strategy.stopped / strategy.crashed
  - sim.order_submitted / sim.order_filled / sim.order_cancelled
  - backtest.started / backtest.done / backtest.failed
  - quote.surge / quote.limit_up         （Step 2 接入）
  - ai.alert.info / ai.alert.warn / ai.alert.danger  （Step 3 接入）
  - api.exception
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.core.pubsub import get_sync_redis
from app.utils.trading_period import now_cn

EVENT_CHANNEL_PREFIX = "events:"


def event_channel(event_type: str) -> str:
    return f"{EVENT_CHANNEL_PREFIX}{event_type}"


def publish_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    user_id: int | None = None,
    level: str = "info",
) -> None:
    """同步发布事件到 Redis。

    Args:
        event_type: 三段式名称，如 "strategy.crashed"
        payload: 任意 JSON 可序列化数据
        user_id: 可选，限制事件只匹配此用户的规则；None 表示广播给所有用户
        level: "info" / "warn" / "danger"，用于 quiet_hours / 优先级过滤
    """
    envelope = {
        "type": event_type,
        "level": level,
        "user_id": user_id,
        "ts": now_cn().isoformat(),
        "payload": payload or {},
    }
    try:
        get_sync_redis().publish(
            event_channel(event_type),
            json.dumps(envelope, ensure_ascii=False),
        )
    except Exception as exc:
        # 事件总线本身不能拖垮业务
        logger.warning("publish_event {} failed: {}", event_type, exc)
