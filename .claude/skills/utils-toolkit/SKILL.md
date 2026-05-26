---
name: utils-toolkit
description: app/utils/* 工具函数 / 日期 / 股票代码 / 交易时段 / 常用库选型。触发词：工具、utils、日期、股票代码、交易时段、限流、辅助、常用函数
---

# 工具函数

## app/utils/ 目录

| 文件 | 用途 |
|---|---|
| `logger.py` | loguru 统一配置（北京时间） |
| `symbol.py` | 股票代码归一化 / 交易所识别 |
| `trading_period.py` | A 股交易时段判断 |

加新工具：单文件单一职责，不要做大杂烩 `common.py`。

## symbol.py 用法

```python
from app.utils.symbol import normalize, exchange, code

normalize("600000")        # "sh600000"
normalize("000001")        # "sz000001"
normalize("sh.600000")     # "sh600000"
normalize("600000.SH")     # "sh600000"
exchange("sh600000")       # "SH"
code("sh600000")           # "600000"
```

所有进入系统的代码必须 `normalize` 一遍。

## trading_period.py 用法

```python
from app.utils.trading_period import is_trading_time, now_cn

if is_trading_time():
    ...
```

更复杂的需求（节假日）用 `pandas-market-calendars`：

```python
import pandas_market_calendars as mcal
xshg = mcal.get_calendar("XSHG")
sched = xshg.schedule(start_date="2026-01-01", end_date="2026-12-31")
```

## 推荐 Python lib

| 需求 | lib | 备注 |
|---|---|---|
| HTTP 异步 | `httpx` | 已装 |
| HTTP 同步 | `httpx` 同样支持 | 一致性 |
| 时间 | `datetime` + `pytz` | tz-aware |
| 交易日历 | `pandas-market-calendars` | A 股用 XSHG |
| 重试 | `tenacity` | 已装；指数退避 |
| 限流 | `aiolimiter` / 自实现 Redis 令牌 | AKShare 必备 |
| DataFrame | `pandas` 2.x | ArcticDB 原生支持 |
| 数组 | `numpy` 2.x | TA 指标 |
| 技术指标 | `TA-Lib` | C 库，性能优 |
| 配置 | `pydantic-settings` | 已装 |
| 日志 | `loguru` | 已装 |
| 加密 / 哈希 | `passlib[bcrypt]` | 已装 |
| JWT | `python-jose[cryptography]` | 已装 |

## 推荐 npm 包（前端）

| 需求 | lib | 备注 |
|---|---|---|
| HTTP | `axios` | 已装 + 拦截器 |
| 服务器状态 | `@tanstack/react-query` | 已装 |
| 客户端状态 | `zustand` | 已装 |
| 路由 | `react-router` v7 | 已装 |
| UI | `antd` v5 | 已装 |
| 样式 | `tailwindcss` v4 | 已装 |
| 日期 | `dayjs` | 已装；AntD 内部用 |
| K 线图 | `lightweight-charts` | 已装 |
| 通用图 | `echarts` + `echarts-for-react` | 已装 |

## 限流模式（多 worker 共享）

```python
import asyncio, time, redis.asyncio as aioredis
from app.config import settings

async def throttle_akshare():
    """每秒最多 N 个请求，跨 worker 共享。"""
    r = aioredis.from_url(settings.redis_url)
    key = "akshare:slot"
    while True:
        if await r.set(key, 1, ex=1, nx=True):
            return
        await asyncio.sleep(0.2)
```

## 重试模式

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
)
def fetch(url):
    ...
```

## 时间使用约定

- 写入 DB / 存储：tz-aware datetime（`Asia/Shanghai`）
- API 出参：ISO 字符串（Pydantic 默认）
- 日志：北京时间（loguru patcher 已注入）
- 比较：永远 tz-aware vs tz-aware，不要混 naive

## 禁止

- ❌ 用 `datetime.now()`（naive），用 `now_cn()`
- ❌ 自实现 retry 死循环（用 tenacity）
- ❌ 把 utils 写成上千行 `common.py` 大杂烩
- ❌ 工具函数依赖 FastAPI / SQLAlchemy（保持纯函数）
