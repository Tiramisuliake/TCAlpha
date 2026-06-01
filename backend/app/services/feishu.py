"""飞书自定义机器人推送（Phase 5 Step 1）。

文档：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
- 自定义机器人 webhook：POST 即可
- 签名密钥可选：HMAC-SHA256(timestamp + "\n" + secret) → base64
- 单机器人限流：100 条/分钟
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import httpx
from loguru import logger

# 简易令牌桶：feishu:rate:{webhook_hash}:{minute_slot} INCR + 60s EXPIRE
_RATE_LIMIT_PER_MIN = 100


def _gen_sign(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _check_rate_limit(webhook: str) -> bool:
    """同一 webhook 每分钟最多 100 条。超额返回 False。"""
    from app.core.pubsub import get_sync_redis

    slot = int(time.time() // 60)
    key = f"feishu:rate:{hashlib.md5(webhook.encode()).hexdigest()[:12]}:{slot}"
    r = get_sync_redis()
    count = int(r.incr(key))
    if count == 1:
        r.expire(key, 70)
    return count <= _RATE_LIMIT_PER_MIN


async def send_card(
    webhook: str,
    secret: str,
    title: str,
    fields: list[dict[str, Any]],
    color: str = "blue",
    request_timeout: float = 5.0,
) -> tuple[bool, str | None]:
    """发送一张飞书交互卡片。

    Args:
        webhook: 完整 webhook URL
        secret: 签名密钥（可空，仅当机器人开启了签名校验时必填）
        title: 卡片标题
        fields: [{"label": "...", "value": "..."}, ...]
        color: blue / green / orange / red / grey / wathet / turquoise / yellow / carmine / violet
        request_timeout: HTTP 超时（秒）

    Returns:
        (success, error_msg)。失败不抛异常，调用方写 NotifyLog 后继续。
    """
    if not webhook:
        return False, "webhook 未配置"

    if not _check_rate_limit(webhook):
        return False, f"超过限流（{_RATE_LIMIT_PER_MIN}/min）"

    elements = []
    for item in fields:
        elements.append({
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{item['label']}**\n{item['value']}",
                    },
                }
            ],
        })

    body: dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements or [{"tag": "div", "text": {"tag": "plain_text", "content": "(空)"}}],
        },
    }

    if secret:
        ts = int(time.time())
        body["timestamp"] = str(ts)
        body["sign"] = _gen_sign(ts, secret)

    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            resp = await client.post(webhook, json=body)
        data = resp.json()
        if data.get("code") not in (0, None) and data.get("StatusCode") not in (0, None):
            return False, f"feishu code={data.get('code')} msg={data.get('msg')}"
        return True, None
    except httpx.HTTPError as exc:
        logger.warning("feishu send_card HTTP error: {}", exc)
        return False, f"HTTP {type(exc).__name__}: {exc}"
    except Exception as exc:
        logger.exception("feishu send_card unexpected")
        return False, f"{type(exc).__name__}: {exc}"


async def send_text(
    webhook: str,
    secret: str,
    content: str,
    request_timeout: float = 5.0,
) -> tuple[bool, str | None]:
    """发送纯文本（测试 / 简短通知用）。"""
    if not webhook:
        return False, "webhook 未配置"
    if not _check_rate_limit(webhook):
        return False, f"超过限流（{_RATE_LIMIT_PER_MIN}/min）"

    body: dict[str, Any] = {"msg_type": "text", "content": {"text": content}}
    if secret:
        ts = int(time.time())
        body["timestamp"] = str(ts)
        body["sign"] = _gen_sign(ts, secret)

    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            resp = await client.post(webhook, json=body)
        data = resp.json()
        if data.get("code") not in (0, None) and data.get("StatusCode") not in (0, None):
            return False, f"feishu code={data.get('code')} msg={data.get('msg')}"
        return True, None
    except httpx.HTTPError as exc:
        logger.warning("feishu send_text HTTP error: {}", exc)
        return False, f"HTTP {type(exc).__name__}: {exc}"
    except Exception as exc:
        logger.exception("feishu send_text unexpected")
        return False, f"{type(exc).__name__}: {exc}"
