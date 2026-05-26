# /backtest — 提交一个回测任务

帮助用户构造一个回测 job 并提交。

## 流程

1. 问：策略类名 + 股票代码 + 时间段 + 初始资金 + 手续费

2. 校验：
   - 策略类是否在 `STRATEGY_CLASSES`
   - 股票代码归一化 (`app.utils.symbol.normalize`)
   - 时间段不超 10 年

3. 三种提交方式让用户选：

### A. 通过 API（推荐）

```bash
curl -X POST http://localhost:8000/api/backtest/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ma_cross 600000 2023",
    "class_name": "MaCrossStrategy",
    "symbol": "sh600000",
    "params": {"fast": 5, "slow": 20},
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "init_capital": 1000000,
    "commission_rate": 0.0003,
    "slippage": 0.01
  }'
```

### B. Python 直接调

```python
from app.tasks.backtest_tasks import run_backtest
# 先 DB 里插一条 BacktestJob（status=pending），再：
r = run_backtest.delay(job_id)
print(r.id)
```

### C. 命令行（脚本，未来实现）

```bash
uv run python -m app.scripts.run_backtest \
  --strategy MaCrossStrategy --symbol sh600000 \
  --start 2023-01-01 --end 2023-12-31 ...
```

4. 监控：
   - `celery -A app.tasks.celery_app inspect active`
   - 查询 PG `SELECT * FROM backtest_jobs ORDER BY id DESC LIMIT 5;`

5. 结果落 `backtest_jobs.result`（JSON），含：
   - total_return / annual_return
   - sharpe / sortino
   - max_drawdown
   - trade_count / win_rate / profit_factor
   - 成交明细在 `backtest_trades`
