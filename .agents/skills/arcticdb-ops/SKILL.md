---
name: arcticdb-ops
description: ArcticDB 时序数据 / K 线 / Tick 存储 / Library 管理 / 批量读写。触发词：ArcticDB、时序、K 线、tick、Library、LMDB、write、read_batch
---

# ArcticDB 操作

## 为什么用 ArcticDB

- 嵌入式 LMDB，无运维
- 列存 + 分块，K 线读写比 PG 快一两个数量级
- 原生 DataFrame 接口
- 数据存本地 `./data/arctic/`，备份 = 拷文件夹

## 单例

```python
from app.db.arctic import get_arctic, get_library

ac = get_arctic()                 # Arctic 实例
lib = get_library("bar_1d")       # 自动建库
```

## Library 命名约定

| Library | 内容 | 索引 |
|---|---|---|
| `bar_1m` | 分钟 K 线 | DatetimeIndex |
| `bar_1d` | 日 K 线 | DatetimeIndex |
| `tick` | Tick 数据 | DatetimeIndex（毫秒） |
| `factor_xxx` | 因子时间序列 | DatetimeIndex |

每个 symbol 是 library 里的一条记录，symbol key 用 `sh600000` 这种归一化代码。

## 写入

```python
import pandas as pd
from app.db.arctic import get_library

df = pd.DataFrame({
    "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...],
}, index=pd.DatetimeIndex([...], name="dt", tz="Asia/Shanghai"))

lib = get_library("bar_1d")
lib.write("sh600000", df)                              # 覆盖
lib.append("sh600000", new_df)                         # 增量
lib.update("sh600000", patch_df)                       # 按 index 更新（去重）
```

**索引必须是单调升序、唯一**；否则 `append` 会失败。

## 读取

```python
lib.read("sh600000").data                              # 全部
lib.read("sh600000", date_range=(start, end)).data     # 范围
lib.read("sh600000", columns=["close", "volume"]).data # 列选

# 批量读多个 symbol
result = lib.read_batch(["sh600000", "sh600001", "sz000001"])
for s, payload in zip(["sh600000", "sh600001", "sz000001"], result):
    df = payload.data
```

## 元数据

```python
lib.write("sh600000", df, metadata={"source": "akshare", "fetched_at": "2026-..."})
v = lib.read("sh600000")
v.metadata
```

## 版本

ArcticDB 自带 versioning：

```python
lib.list_versions("sh600000")
lib.read("sh600000", as_of=2)                  # 历史版本
lib.prune_previous_versions("sh600000")        # 清理
```

正常业务不需要 versioning，写完可以 prune 节约空间。

## 与 PG 分工

| 数据 | 存哪 |
|---|---|
| K 线 / Tick | ArcticDB |
| 因子时间序列 | ArcticDB |
| 股票元数据（代码、名称、行业） | PG |
| 策略元数据 / 状态 | PG |
| 订单 / 持仓 / 回测结果 | PG |
| 用户 / 权限 | PG |

## 性能要点

- 批量读写永远比循环单条快 10×
- 列选 `columns=[...]` 大幅减少 IO
- `date_range` 利用分块跳过无关数据
- 不要把策略实时计算结果频繁回写（在内存里聚合后落库）

## 备份

```bash
# 直接拷贝 data/arctic/ 文件夹
tar czf arctic-backup-$(date +%Y%m%d).tgz data/arctic/
```

## 禁止

- ❌ 用 ArcticDB 存关系型数据（用 PG）
- ❌ 把 ArcticDB URI 改成 S3 但本地数据没迁移
- ❌ 多进程同时写一个 symbol（用 Celery 串行 + Redis 锁）
- ❌ 写非单调索引
