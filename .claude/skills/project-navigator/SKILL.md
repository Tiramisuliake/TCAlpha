---
name: project-navigator
description: TCAlpha 项目结构速查 / 文件位置 / 代码导航。触发词：项目结构、在哪里、怎么找、代码位置、目录、文件、导航、定位
---

# TCAlpha 项目导航

## 顶层

```
tcalpha/
├── backend/        FastAPI + Celery + ArcticDB
├── frontend/       React + Vite + AntD
├── docker-compose.yml   PG + Redis
├── .env.example
├── Makefile        快捷命令
└── .claude/        本配置
```

## backend/ 关键文件速查

| 想做 | 文件 |
|---|---|
| 全局配置（DB URL、CORS 等） | `app/config.py` |
| FastAPI 入口 + 路由挂载 | `app/main.py` |
| Depends（DB session / current user） | `app/deps.py` |
| 加新路由 | `app/api/<x>.py` + `app/main.py` 挂载 |
| 加业务逻辑 | `app/services/<x>.py` |
| 加 DTO | `app/schemas/<x>.py` |
| 加 ORM 模型 | `app/db/models/<x>.py` + `__init__.py` 导出 |
| Alembic 迁移 | `alembic/versions/`（autogenerate 生成） |
| ArcticDB 单例 | `app/db/arctic.py` |
| Redis 客户端 | `app/db/redis_client.py` |
| PG 引擎 / Base | `app/db/postgres.py` |
| Celery 实例 + beat | `app/tasks/celery_app.py` |
| 加 Celery 任务 | `app/tasks/<x>_tasks.py` + `celery_app.py` include |
| 加策略类 | `app/strategies/examples/<x>.py` 继承 `StrategyBase` |
| 策略基类 | `app/strategies/base.py` |
| 回测引擎 | `app/core/backtest_engine.py` |
| 模拟撮合 | `app/core/sim_gateway.py` |
| Gateway 抽象 | `app/core/gateway.py` |
| 指标插件 | `app/indicators/<x>.py` |
| 工具函数 | `app/utils/<x>.py` |
| 测试 | `tests/test_<x>.py` |

## frontend/ 关键文件速查

| 想做 | 文件 |
|---|---|
| 应用入口 + Provider | `src/main.tsx` |
| Shell + 路由 | `src/App.tsx` |
| 加新页面 | `src/pages/<X>/index.tsx` + 在 `App.tsx` 加 Route 和侧栏菜单 |
| 加 API 调用 | `src/api/<x>.ts` + `src/types/index.ts` 类型 |
| Axios 客户端 + 拦截 | `src/api/client.ts` |
| Zustand store | `src/store/<x>.ts` |
| 自定义 hook | `src/hooks/<x>.ts` |
| Tailwind / 全局 CSS | `src/styles/index.css` |
| Vite 代理 | `vite.config.ts` |

## 功能 → 文件链路

### 新增 "查询股票列表" 功能

```
db/models/symbol.py        ORM
alembic revision …         迁移
schemas/market.py          DTO
services/market.py         业务（查 PG → cache 30s）
api/market.py              GET /api/market/symbols
─────
frontend/src/types/index.ts  类型
frontend/src/api/market.ts   调用函数
frontend/src/pages/Data/...  页面用 useQuery
```

### 新增定时任务

```
tasks/<name>_tasks.py      @celery_app.task
tasks/celery_app.py        include + beat_schedule cron
```

### 新增策略类

```
strategies/examples/<x>.py 继承 StrategyBase
（运行）走 services/strategy + tasks/strategy_tasks
```

## 代码搜索技巧

| 想找什么 | 命令 |
|---|---|
| 所有 endpoint | `grep -rn "router\.\(get\|post\|put\|delete\)" backend/app/api` |
| 所有 ORM 模型 | `grep -rn "__tablename__" backend/app/db/models` |
| 所有 Celery 任务 | `grep -rn "@celery_app.task" backend/app/tasks` |
| 所有 service 函数 | `grep -rn "^async def\|^def " backend/app/services` |
| 前端所有 API 调用 | `grep -rn "api\.\(get\|post\|put\|delete\)" frontend/src/api` |
| 前端所有路由 | `grep -n "<Route " frontend/src/App.tsx` |

## 常见错误

| ❌ | ✅ |
|---|---|
| 直接改 alembic 已 head 的迁移文件 | 写新迁移（autogenerate 或 手写） |
| 在 endpoint 里查 ArcticDB 大数据 | 把查询挪到 service + 缓存 |
| 前端在 component 里直接 axios | 放到 src/api/*.ts |
| 跨页面共享状态用 props 透传 | 提到 Zustand store |
