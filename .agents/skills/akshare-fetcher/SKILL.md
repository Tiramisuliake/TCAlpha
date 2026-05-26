---
name: akshare-fetcher
description: AKShare 数据下载 / 限流 / 历史 K 线 / 实时报价 / 重试 / 落 ArcticDB。触发词：AKShare、数据下载、行情、历史 K 线、实时报价、限流、ak、数据源
---

# AKShare 数据获取

## 设计原则

1. **永远走 Celery 任务**，不在 endpoint 里直接调（AKShare 慢且易限流）
2. **全局限流**：Redis 令牌桶，跨 worker 共享
3. **重试 + 退避**：`tenacity` 指数退避
4. **失败要可见**：写 `data_jobs` 表或日志
5. **结果落 ArcticDB**：用 normalized symbol 作 key

## 常用接口（A 股）

| 数据 | 函数 | 备注 |
|---|---|---|
| 股票列表 | `ak.stock_zh_a_spot_em()` | 5 千+ 行，慢，缓存 1 天 |
| 日 K | `ak.stock_zh_a_hist(symbol, period="daily", ...)` | 复权 `adjust="qfq"` |
| 分钟 K | `ak.stock_zh_a_hist_min_em(symbol, period="1", ...)` | 1/5/15/30/60 分 |
| 实时报价 | `ak.stock_zh_a_spot_em()` | 全市场快照 |
| 分时 | `ak.stock_intraday_em(symbol)` | tick 级 |
| 指数 | `ak.index_zh_a_hist(symbol)` | |
| 基本面 | `ak.stock_individual_info_em(symbol)` | |

## symbol 格式坑

AKShare 不同接口 symbol 格式不一样！

| 接口 | 接受 |
|---|---|
| `stock_zh_a_hist` | `"600000"`（裸 6 位） |
| `stock_zh_a_hist_min_em` | `"sh600000"`（带前缀） |
| `stock_intraday_em` | `"sh600000"` |
| `index_zh_a_hist` | `"sh000001"` |

封一层 adapter，进系统前归一化为 `sh600000`，调 AKShare 时按接口需要转换：

```python
from app.utils.symbol import normalize, code

def to_ak_hist(s: str) -> str:
    return code(normalize(s))   # 6 位裸代码

def to_ak_min(s: str) -> str:
    return normalize(s)         # sh600000
```

## 下载日 K 模板

```python
import akshare as ak
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.utils.symbol import normalize, code
from app.db.arctic import get_library


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = ak.stock_zh_a_hist(
        symbol=code(symbol), period="daily",
        start_date=start.replace("-", ""), end_date=end.replace("-", ""),
        adjust="qfq",
    )
    df.columns = ["dt", "open", "close", "high", "low", "volume", "amount",
                  "amplitude", "pct_chg", "change", "turnover"]
    df["dt"] = pd.to_datetime(df["dt"]).dt.tz_localize("Asia/Shanghai")
    df = df.set_index("dt").sort_index()
    return df[["open", "high", "low", "close", "volume", "amount"]]


def save_daily(symbol: str, df: pd.DataFrame) -> None:
    lib = get_library("bar_1d")
    s = normalize(symbol)
    if s in lib.list_symbols():
        existing = lib.read(s).data
        df = pd.concat([existing, df]).pipe(lambda x: x[~x.index.duplicated(keep="last")])
        df = df.sort_index()
    lib.write(s, df, metadata={"source": "akshare", "fetched_at": datetime.now().isoformat()})
```

## Celery 任务

```python
@celery_app.task(bind=True, max_retries=3, name="app.tasks.data_tasks.download_daily")
def download_daily(self, symbol: str, start: str, end: str) -> dict:
    try:
        wait_for_rate_limit()             # Redis 令牌
        df = fetch_daily(symbol, start, end)
        save_daily(symbol, df)
        return {"symbol": symbol, "rows": len(df)}
    except RateLimited as e:
        raise self.retry(exc=e, countdown=5)
```

## 全局限流（Redis 令牌）

```python
import redis, time
from app.config import settings

_r = redis.from_url(settings.redis_url)

def wait_for_rate_limit(max_per_sec: int = 2) -> None:
    while True:
        # 每秒最多 max_per_sec 个 worker 拿到令牌
        slot = int(time.time())
        key = f"ak:slot:{slot}"
        cnt = _r.incr(key)
        if cnt == 1:
            _r.expire(key, 2)
        if cnt <= max_per_sec:
            return
        time.sleep(0.2)
```

或用 `aiolimiter`（async 场景）。

## 数据完整性检查

下载后必须：
- 行数 > 0
- index 单调递增
- 没有 NaN（收盘价不能 NaN）
- 时间范围覆盖请求范围

否则记 log + 不写入 + 重试。

## 禁止

- ❌ 在 FastAPI endpoint 里直接调 AKShare
- ❌ 不限流批量并发
- ❌ 不重试网络错
- ❌ 把 AKShare 原始字段直接落 ArcticDB（必须先 rename + 类型转换）
- ❌ 同一 symbol 多 worker 同时写（用 Redis 锁串行）
