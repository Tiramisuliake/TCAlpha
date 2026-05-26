---
name: celery-tasks
description: Celery 任务 / worker / beat 调度 / Redis broker / 任务设计模式。触发词：Celery、任务、task、worker、beat、定时、调度、broker、后台任务、异步
---

# Celery 任务

## 启动

```bash
make worker     # uv run celery -A app.tasks.celery_app worker -l info
make beat       # uv run celery -A app.tasks.celery_app beat -l info
```

Windows 注意：Celery 5 在 Windows 上需要 `--pool=solo` 或 `--pool=threads`，否则 worker 跑不起来。

```bash
celery -A app.tasks.celery_app worker -l info --pool=solo   # 开发期
```

## 加任务

1. 在 `app/tasks/<name>_tasks.py` 写：

```python
from app.tasks.celery_app import celery_app
from loguru import logger

@celery_app.task(name="app.tasks.data_tasks.download_one_symbol", bind=True, max_retries=3)
def download_one_symbol(self, symbol: str, period: str = "1d") -> dict:
    try:
        # ... 调 AKShare → 写 ArcticDB
        return {"symbol": symbol, "ok": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

2. 在 `app/tasks/celery_app.py` 的 `include=[...]` 加入新模块路径。

3. 重启 worker。

## 任务命名

强烈建议显式 `name="app.tasks.x_tasks.fn"`，避免不同导入路径下被注册成不同任务。

## 触发方式

```python
# 立即异步执行
from app.tasks.data_tasks import download_one_symbol
result = download_one_symbol.delay("sh600000", "1d")    # AsyncResult
task_id = result.id

# 带选项
download_one_symbol.apply_async(args=["sh600000"], countdown=60, queue="data")

# 查状态
from celery.result import AsyncResult
r = AsyncResult(task_id)
r.state           # PENDING / STARTED / SUCCESS / FAILURE / RETRY
r.result          # 返回值 或 异常
```

## Beat 调度

```python
# app/tasks/celery_app.py
celery_app.conf.beat_schedule = {
    "daily-download": {
        "task": "app.tasks.data_tasks.download_daily_kline_all",
        "schedule": crontab(hour=20, minute=0),   # 每日 20:00
    },
    "every-30s": {
        "task": "app.tasks.x_tasks.poll_x",
        "schedule": 30.0,                          # 秒
    },
}
```

时区由 `timezone="Asia/Shanghai"` + `enable_utc=False` 控制。

## 设计原则

| 场景 | 选型 |
|---|---|
| 短小（< 100ms） | 不用 Celery，直接 endpoint 内做 |
| 阻塞 IO 任务 | Celery worker（`--pool=threads` 提升并发） |
| CPU 密集（回测） | Celery worker（`--pool=prefork`，多进程） |
| 长跑（实时策略） | 单独 worker + 长 timeout |
| 实时性要求高 | 不适合 Celery，用 WS / Redis pub/sub |

## 限流

AKShare 全局限流（多 worker 共享）：

```python
import redis
from app.config import settings

r = redis.from_url(settings.redis_url)

def acquire_akshare_slot():
    key = "akshare:rate"
    if not r.set(key, 1, ex=1, nx=True):  # 简易令牌
        raise self.retry(countdown=1)
```

或用 `celery-singleton` 强制单实例运行。

## 幂等性

任务可能被重复执行（worker 崩溃、`acks_late`）。设计为幂等：

- 用业务唯一键去重
- ArcticDB / PG 写之前先查
- 配合 Redis SETNX 锁

## 错误处理

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def x(self):
    try:
        ...
    except RetryableError as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    except FatalError:
        logger.exception("fatal, won't retry")
        raise   # 进入 FAILURE
```

## 监控

- `celery -A app.tasks.celery_app inspect active`
- `celery -A app.tasks.celery_app inspect scheduled`
- 后期接入 flower：`celery -A app.tasks.celery_app flower`

## 禁止

- ❌ Celery 任务里建 AsyncSession（用同步 session 或重新组织）
- ❌ 任务里直接 print（用 loguru）
- ❌ 任务超过 1 小时不分片
- ❌ 不设 `time_limit` 跑可能死循环的任务
