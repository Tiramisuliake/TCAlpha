---
name: error-handler
description: 异常处理 / 全局 handler / HTTPException / loguru 日志策略。触发词：异常、错误、Error、try-catch、HTTPException、日志、log、捕获、handler、500
---

# 错误处理

## 三类错误对应三种处理

| 错误类型 | 处理 |
|---|---|
| 用户输入错（参数缺失/格式错） | Pydantic 自动 422，无需手写 |
| 业务规则违反（重复 / 余额不足 / 找不到） | `raise HTTPException(4xx)` |
| 系统/外部错（DB 挂 / AKShare 限流 / 第三方超时） | 全局 handler + 日志 + 5xx |

## HTTPException 模板

```python
from fastapi import HTTPException, status

if not user:
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user not found")

if balance < amount:
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"code": "INSUFFICIENT_BALANCE", "balance": balance, "needed": amount},
    )
```

`detail` 可以是字符串或 dict（前端能解析结构）。

## 自定义业务异常（推荐）

```python
# app/exceptions.py
class TCError(Exception):
    code: str = "tc_error"
    status_code: int = 400

class SymbolNotFound(TCError):
    code = "symbol_not_found"
    status_code = 404

class AKShareRateLimited(TCError):
    code = "akshare_rate_limited"
    status_code = 429
```

全局 handler（`main.py`）：

```python
from fastapi.responses import JSONResponse
from app.exceptions import TCError

@app.exception_handler(TCError)
async def tc_error_handler(req, exc: TCError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": str(exc)},
    )

@app.exception_handler(Exception)
async def unhandled(req, exc: Exception):
    logger.exception("unhandled: {} {}", req.method, req.url.path)
    return JSONResponse(status_code=500, content={"code": "internal_error", "detail": "服务器内部错误"})
```

## loguru 日志策略

```python
from loguru import logger

logger.info("user {} login from {}", uid, ip)               # f-string 优于格式化
logger.warning("akshare slow: {:.2f}s symbol={}", dt, s)
logger.exception("backtest failed job={}", job_id)          # 自动带 traceback
```

不同级别：

| 级别 | 何时 |
|---|---|
| DEBUG | 临时排查（提交前移除） |
| INFO | 正常业务事件（登录、任务启动） |
| WARNING | 异常但可恢复（重试中、降级） |
| ERROR | 业务失败（订单拒绝、回测异常） |
| CRITICAL | 系统级（DB 失联） |

## try / except 原则

```python
# ✅ 精准
try:
    df = ak.stock_zh_a_hist(symbol)
except requests.HTTPError as e:
    if e.response.status_code == 429:
        raise AKShareRateLimited("rate limited") from e
    raise
except (requests.Timeout, requests.ConnectionError) as e:
    raise AKShareUnavailable("network") from e
```

```python
# ❌ 兜底吞错
try:
    do_x()
except Exception:
    pass
```

```python
# ❌ 太宽
try:
    do_x()
except Exception as e:
    return None
```

## Celery 任务里

```python
@celery_app.task(bind=True, max_retries=3)
def x(self):
    try:
        ...
    except RetryableError as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    except FatalError:
        logger.exception("fatal")
        raise   # 标记 FAILURE
```

## 前端处理

axios 拦截器（`src/api/client.ts`）已统一弹 message。组件层只需 try/catch 关注业务分支：

```ts
try {
  const data = await getKline(symbol);
} catch (e) {
  // message 已弹，这里只做状态回退
  setLoading(false);
}
```

## 禁止

- ❌ `except: pass`
- ❌ `print(traceback.format_exc())` 调试残留
- ❌ 日志里写明文 token / 密码 / API Key
- ❌ 500 错误把 stack trace 返回给前端
