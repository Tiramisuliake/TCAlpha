"""Redis 共享限流工具。

简单固定窗口算法：每秒一个 Redis key 计数；超过 `rate_per_sec` 阻塞轮询。
跨 Celery worker 进程共享，适合 AKShare / OpenAI 等外部 API 限流。

注意：固定窗口在秒边界附近允许双倍突发（s 末和 s+1 初）；
对 AKShare 2 req/s 这种宽松限制可接受。需要严格平滑可换令牌桶。
"""
from __future__ import annotations

import time

import redis as _redis

from app.config import settings

_r: _redis.Redis | None = None


def get_redis() -> _redis.Redis:
    global _r
    if _r is None:
        _r = _redis.from_url(settings.redis_url, decode_responses=True)
    return _r


def acquire(
    key_prefix: str,
    rate_per_sec: int,
    poll_interval: float = 0.3,
    max_wait: float = 30.0,
) -> None:
    """阻塞直到本进程能在当前秒拿到一个配额。

    - key_prefix: Redis key 命名空间（如 "ak"）；同 prefix 多 worker 共享配额
    - rate_per_sec: 每秒最大调用次数
    - poll_interval: 配额满时的轮询间隔
    - max_wait: 安全上限，避免极端拥塞下死等

    超过 max_wait 抛 TimeoutError。
    """
    deadline = time.monotonic() + max_wait
    r = get_redis()
    while True:
        slot = int(time.time())
        key = f"{key_prefix}:slot:{slot}"
        cnt = int(r.incr(key))
        if cnt == 1:
            # 多留 1 秒过期，避免边界时钟漂移导致 key 被提前清
            r.expire(key, 2)
        if cnt <= rate_per_sec:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"rate_limit acquire timeout: prefix={key_prefix} "
                f"rate={rate_per_sec}/s waited>{max_wait}s"
            )
        time.sleep(poll_interval)


def wait_for_akshare() -> None:
    """AKShare 专用：使用 settings.akshare_rate_limit 配置。"""
    acquire("ak", settings.akshare_rate_limit)
