"""通知分发 worker（Phase 5 Step 1）。

- asyncio Redis psubscribe `events:*`
- 收到事件 → 查所有匹配的 NotifyRule → 按 channels 分发
- 每次推送写 NotifyLog 历史
- 30s 防抖去重（同一 type+payload hash）

启动：
    uv --directory backend run python -m app.workers.notify_dispatcher
    或 make notify
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import signal
from datetime import time as dtime
from typing import Any

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.core.event_bus import EVENT_CHANNEL_PREFIX
from app.db.models.notify import NotifyLog, NotifyRule
from app.db.postgres import SyncSessionLocal
from app.services import feishu as feishu_svc
from app.utils.trading_period import now_cn

DEDUPE_TTL_S = 30


# ── 工具 ──────────────────────────────────────────────────────────────


def _match_event_type(rule_types: list[str], event_type: str) -> bool:
    """支持通配符 'strategy.*' 'ai.alert.*'。"""
    return any(fnmatch.fnmatch(event_type, pattern) for pattern in rule_types)


def _is_quiet_now(quiet_hours: str) -> bool:
    """格式 'HH:MM-HH:MM'，跨天用 '22:00-08:00'。空串 = 不静音。"""
    if not quiet_hours or "-" not in quiet_hours:
        return False
    try:
        start_s, end_s = quiet_hours.split("-")
        sh, sm = (int(x) for x in start_s.strip().split(":"))
        eh, em = (int(x) for x in end_s.strip().split(":"))
        start = dtime(sh, sm)
        end = dtime(eh, em)
    except (ValueError, AttributeError):
        logger.warning("invalid quiet_hours: {}", quiet_hours)
        return False
    now = now_cn().time()
    if start <= end:
        return start <= now < end
    # 跨天
    return now >= start or now < end


def _dedupe_key(event_type: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"t": event_type, "p": payload}, sort_keys=True, ensure_ascii=False)
    return f"notify:dedupe:{hashlib.md5(raw.encode()).hexdigest()[:16]}"


def _event_to_card(envelope: dict[str, Any]) -> tuple[str, list[dict], str]:
    """把事件信封翻译成飞书卡片标题/字段/颜色。"""
    event_type: str = envelope["type"]
    level: str = envelope.get("level", "info")
    payload: dict = envelope.get("payload") or {}
    ts = envelope.get("ts", "")

    color = {"info": "blue", "warn": "orange", "danger": "red"}.get(level, "grey")
    title = f"[{level.upper()}] {event_type}"

    fields = [
        {"label": "事件", "value": event_type},
        {"label": "时间", "value": ts.replace("T", " ").split(".")[0] if ts else "—"},
    ]
    # payload 平铺前 6 个字段
    for k, v in list(payload.items())[:6]:
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        fields.append({"label": str(k), "value": str(v)[:200]})

    return title, fields, color


# ── 主逻辑 ────────────────────────────────────────────────────────────


async def _log_notify(
    *,
    user_id: int,
    rule_id: int | None,
    event_type: str,
    channel: str,
    payload: dict,
    success: bool,
    error_msg: str = "",
) -> None:
    def _write() -> None:
        with SyncSessionLocal() as db:
            db.add(NotifyLog(
                user_id=user_id,
                rule_id=rule_id,
                event_type=event_type,
                channel=channel,
                payload=payload,
                success=success,
                error_msg=error_msg,
            ))
            db.commit()
    await asyncio.to_thread(_write)


def _load_active_rules() -> list[NotifyRule]:
    """同步加载所有启用规则（dispatcher 自己缓存 5s 也行，这里每事件查一次足够）。"""
    with SyncSessionLocal() as db:
        rows = db.execute(
            select(NotifyRule).where(NotifyRule.enabled.is_(True))
        ).scalars().all()
        # detach 出 session 后还要用属性，提前抓取
        return [
            NotifyRule(
                id=r.id,
                user_id=r.user_id,
                name=r.name,
                match_types=list(r.match_types or []),
                match_filters=dict(r.match_filters or {}),
                channels=list(r.channels or []),
                feishu_webhook=r.feishu_webhook,
                feishu_secret=r.feishu_secret,
                quiet_hours=r.quiet_hours,
                enabled=r.enabled,
            )
            for r in rows
        ]


async def _handle_event(redis_async: aioredis.Redis, raw: str) -> None:
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("non-json event: {}", raw[:120])
        return

    event_type: str = envelope.get("type", "")
    payload: dict = envelope.get("payload") or {}
    event_user_id: int | None = envelope.get("user_id")

    # 去重
    dkey = _dedupe_key(event_type, payload)
    if not await redis_async.set(dkey, "1", ex=DEDUPE_TTL_S, nx=True):
        logger.debug("dedup skip: {}", event_type)
        return

    rules = await asyncio.to_thread(_load_active_rules)
    if not rules:
        return

    title, fields, color = _event_to_card(envelope)

    for rule in rules:
        # user 过滤
        if event_user_id is not None and rule.user_id != event_user_id:
            continue
        # type 匹配
        if not _match_event_type(rule.match_types, event_type):
            continue
        # 静音
        if _is_quiet_now(rule.quiet_hours):
            logger.info("rule {} muted by quiet_hours", rule.id)
            continue
        # 渠道分发
        for channel in rule.channels:
            if channel == "feishu":
                ok, err = await feishu_svc.send_card(
                    rule.feishu_webhook,
                    rule.feishu_secret,
                    title=title,
                    fields=fields,
                    color=color,
                )
                await _log_notify(
                    user_id=rule.user_id,
                    rule_id=rule.id,
                    event_type=event_type,
                    channel=channel,
                    payload=payload,
                    success=ok,
                    error_msg=err or "",
                )
                if ok:
                    logger.info("→ feishu rule={} event={} ok", rule.id, event_type)
                else:
                    logger.warning("→ feishu rule={} event={} failed: {}", rule.id, event_type, err)
            else:
                logger.debug("channel {} not yet implemented", channel)


async def run() -> None:
    redis_async = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_async.pubsub()
    pattern = f"{EVENT_CHANNEL_PREFIX}*"
    await pubsub.psubscribe(pattern)
    logger.info("notify_dispatcher subscribed pattern={}", pattern)

    stop = asyncio.Event()

    def _signal_stop(*_: Any) -> None:
        logger.info("notify_dispatcher signal stop")
        stop.set()

    try:
        signal.signal(signal.SIGINT, _signal_stop)
        signal.signal(signal.SIGTERM, _signal_stop)
    except (ValueError, AttributeError):
        # 子线程或 Windows 等场景注册可能受限
        pass

    try:
        async for msg in pubsub.listen():
            if stop.is_set():
                break
            if msg.get("type") != "pmessage":
                continue
            data = msg.get("data")
            if not isinstance(data, str):
                continue
            try:
                await _handle_event(redis_async, data)
            except Exception:
                logger.exception("handle_event failed for: {}", data[:200])
    finally:
        await pubsub.punsubscribe(pattern)
        await pubsub.close()
        await redis_async.close()
        logger.info("notify_dispatcher exited")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
