"""Redis 限流工具测试（B5）。

用 FakeRedis 替换真 Redis 客户端，断言：
- 配额内 acquire 立即返回
- 配额满 → 进入轮询；mock time.sleep 不真睡
- 超过 max_wait → 抛 TimeoutError
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from app.utils import rate_limit


class FakeRedis:
    """支持 incr / expire / get 的最小内存 Redis。"""

    def __init__(self) -> None:
        self._store: dict[str, int] = defaultdict(int)

    def incr(self, key: str) -> int:
        self._store[key] += 1
        return self._store[key]

    def expire(self, key: str, _ttl: int) -> None:
        pass  # 测试中不模拟过期


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    fr = FakeRedis()
    monkeypatch.setattr(rate_limit, "_r", fr, raising=False)
    monkeypatch.setattr(rate_limit, "get_redis", lambda: fr)
    return fr


def test_acquire_within_limit_returns_immediately(fake_redis, monkeypatch):
    """配额 5，连续调 5 次立即返回；不应进入 sleep。"""
    sleep_calls = []
    monkeypatch.setattr(rate_limit.time, "sleep", lambda s: sleep_calls.append(s))

    for _ in range(5):
        rate_limit.acquire("test", rate_per_sec=5)

    assert sleep_calls == [], "配额内不应触发 sleep"


def test_acquire_blocks_when_over_limit(fake_redis, monkeypatch):
    """配额 2，第 3 次开始进入轮询；mock sleep 让它在第 4 次轮询时新 slot 命中。"""
    sleep_calls = []
    # 模拟时间推进：每次 sleep 后 int(time.time()) 进入下一秒（fake_redis 也跟着换 key）
    clock = [1_000_000.0]

    def fake_time():
        return clock[0]

    def fake_sleep(s):
        sleep_calls.append(s)
        clock[0] += 1.0  # 跳到下一秒

    monkeypatch.setattr(rate_limit.time, "time", fake_time)
    monkeypatch.setattr(rate_limit.time, "sleep", fake_sleep)
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])

    # 1, 2 立即过；3 阻塞 → fake_sleep 推进 1 秒 → 新 slot → 1 → 通过
    for _ in range(3):
        rate_limit.acquire("ak", rate_per_sec=2, poll_interval=0.1)

    assert len(sleep_calls) >= 1


def test_acquire_timeout(fake_redis, monkeypatch):
    """配额 0 → 永远拿不到 → max_wait 后 TimeoutError。"""
    clock = [1_000_000.0]
    monkeypatch.setattr(rate_limit.time, "time", lambda: clock[0])
    # monotonic 持续推进，sleep 不再增加 wall 时间
    monkeypatch.setattr(rate_limit.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])

    with pytest.raises(TimeoutError):
        rate_limit.acquire("ak", rate_per_sec=0, poll_interval=0.1, max_wait=0.5)


def test_wait_for_akshare_uses_settings(fake_redis, monkeypatch):
    """wait_for_akshare 默认走 settings.akshare_rate_limit。"""
    called = {}

    def fake_acquire(prefix, rate, **_kw):
        called["prefix"] = prefix
        called["rate"] = rate

    monkeypatch.setattr(rate_limit, "acquire", fake_acquire)
    monkeypatch.setattr("app.config.settings.akshare_rate_limit", 5)

    rate_limit.wait_for_akshare()
    assert called == {"prefix": "ak", "rate": 5}
