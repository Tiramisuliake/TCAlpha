---
name: bug-detective
description: 报错排查 / 异常定位 / 调试 / 性能问题诊断。触发词：Bug、报错、不工作、调试、排查、为什么、出问题、失败、不生效、无效、定位问题
---

# Bug 排查

## 通用步骤

1. **复现**：明确"做什么 → 期待什么 → 实际什么"
2. **看日志**：loguru 输出 / 浏览器 console / Network / Celery worker log
3. **定位层**：前端 → API → service → DB / Celery / ArcticDB
4. **二分**：注释一半代码再跑，看错误是否消失
5. **修复**：先理解根因再改，不要瞎试

## TCAlpha 常见错误清单

### FastAPI / Pydantic

| 症状 | 可能原因 |
|---|---|
| `422 Unprocessable Entity` | DTO 字段类型不匹配 / 必填字段缺失 |
| `307 Temporary Redirect` | 路由路径多/少尾部 `/` |
| `RuntimeError: There is no current event loop` | 同步代码里调 async 函数，需 `asyncio.run` |
| `DetachedInstanceError` | session 已关闭后访问 ORM 对象的延迟属性 |

### SQLAlchemy

| 症状 | 解决 |
|---|---|
| `greenlet_spawn has not been called` | async session 里用了同步 lazy load，改成 `selectinload` |
| `MissingGreenlet` | 在 lifespan / Celery 同步上下文里用了 async engine，需切 sync |
| `IntegrityError` | 唯一约束 / 外键 / NOT NULL 冲突，检查 alembic 迁移 |
| 查询返回空但 DB 有数据 | filter 条件类型错（如 int vs str 比较）/ session 不同 |

### Alembic

| 症状 | 解决 |
|---|---|
| autogenerate 没有发现新表 | 模型没在 `app/db/models/__init__.py` import |
| 迁移降级报错 | 写 downgrade 时漏字段，对照 upgrade 反操作 |
| 已 head 还提示 multiple heads | `alembic merge -m "merge" head1 head2` |

### Celery

| 症状 | 排查方向 |
|---|---|
| task 不执行 | worker include 列表是否含模块；broker URL 是否对 |
| beat 不触发 | beat 进程是否在跑；时区是否对（`Asia/Shanghai`） |
| task 卡住 | 是否阻塞调用（同步 IO）；改用 `gevent` worker 或拆任务 |
| 重复执行 | 没设 `acks_late=False` 且任务非幂等 → 加去重 key 到 Redis |

### ArcticDB

| 症状 | 解决 |
|---|---|
| `LibraryNotFound` | 调 `get_arctic().create_library('bar_1d')` |
| 写入慢 | 用 `library.write_batch()` 批量；或 `append=True` 增量 |
| 数据顺序错乱 | DataFrame 索引必须是 `DatetimeIndex` 且单调升序 |

### AKShare

| 症状 | 解决 |
|---|---|
| `HTTPError 429` | 触发限流，加 `tenacity` 指数退避 + 全局 Redis 限速 |
| 字段名变了 | AKShare 接口变动频繁，加单元测试守护 |
| 返回空 DataFrame | 股票代码格式不对（带前缀 sh/sz） |

### React / Vite

| 症状 | 排查 |
|---|---|
| CORS error | 后端 `cors_origins` 是否含 vite 端口；浏览器是否走代理 |
| Hook 报 "called conditionally" | 不能在 if/return 后写 Hook，提到组件顶层 |
| AntD ConfigProvider locale 未生效 | 确保 ConfigProvider 包在 BrowserRouter 外层 |
| React Query stale data | 调 `queryClient.invalidateQueries({ queryKey })` |

### WebSocket

| 症状 | 解决 |
|---|---|
| 1006 异常关闭 | Nginx `proxy_read_timeout` 调大；client 加心跳 |
| 多 worker 收不到广播 | 必须 Redis pub/sub，单进程内 dict 不行 |

## 调试技巧

- 后端：`loguru.logger.debug("var={}", var)`，临时改 `setup_logger` 级别为 DEBUG
- 前端：`console.log` + React Devtools / Network 面板
- Celery：`celery -A app.tasks.celery_app inspect active` 看活动任务
- PG：`SELECT * FROM pg_stat_activity` 看慢查询
- ArcticDB：`library.list_symbols()` 验证写入

## 重要：先验证假设再改代码

把"我以为是 X 错"的假设用一行代码或一条命令验证；80% 的 bug 排查时间是花在改了错的地方上。
