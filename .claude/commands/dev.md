# /dev — 开发新功能（全栈生成）

引导完成 TCAlpha 一个新功能的全栈代码生成：后端 ORM + 迁移 + Schema + Service + Route + 前端 Type + API + Page + 路由 + 菜单。

## 流程

### 1. 询问需求

用 AskUserQuestion：
- 功能名称（中文 + 英文 slug）
- 需要哪些后端能力：
  - 数据库表（CRUD）
  - Celery 任务
  - WebSocket / SSE
  - ArcticDB 读写
  - AKShare 调用
- 前端要不要新页面（如要：在哪个菜单层级）

### 2. 检查是否已有

```bash
# 后端
grep -rn "<keyword>" backend/app/api backend/app/services backend/app/db/models
# 前端
grep -rn "<keyword>" frontend/src/pages frontend/src/api
```

如果已有→建议增强；如果没有→继续。

### 3. 读参考

- `backend/app/db/models/strategy.py` 看 ORM 范式
- `backend/app/api/health.py` 看路由范式
- `frontend/src/pages/Dashboard/index.tsx` 看页面范式
- `frontend/src/api/market.ts` 看 API 封装范式

### 4. 输出生成计划

```markdown
## 生成方案：<功能名>

### 后端
1. `backend/app/db/models/<x>.py` — ORM
2. `backend/app/db/models/__init__.py` — re-export
3. `make revision m="add <x>"` — alembic 迁移
4. `backend/app/schemas/<x>.py` — Pydantic DTO（In/Out）
5. `backend/app/services/<x>.py` — 业务逻辑
6. `backend/app/api/<x>.py` — 路由
7. `backend/app/main.py` — include_router
8. `backend/tests/test_<x>.py` — 测试

### 前端
9. `frontend/src/types/index.ts` — 类型
10. `frontend/src/api/<x>.ts` — API 调用
11. `frontend/src/pages/<X>/index.tsx` — 页面
12. `frontend/src/App.tsx` — 路由 + 菜单项

### 若需要
- Celery 任务：`backend/app/tasks/<x>_tasks.py` + celery_app.py include
- WebSocket：在 `backend/app/api/ws.py` 加 endpoint + 前端用 `useWebSocket`

确认开始生成？
```

### 5. 生成（按上述顺序）

每生成完一个文件简短说明改了什么。生成完后跑：

```bash
cd backend && uv run ruff check . && uv run mypy app
cd frontend && pnpm typecheck
```

### 6. 完成报告

```markdown
## 已完成

### 后端
- 新 ORM：StrategyConfig
- 新迁移：alembic/versions/xxx_add_strategy.py
- 新路由：GET /api/strategy/list, POST /api/strategy
- 新测试：test_strategy.py（3 用例）

### 前端
- 新页面：/strategy
- 新菜单项：策略管理
- 新 API：getStrategies / createStrategy

### 后续
- `make migrate` 应用迁移
- 重启 backend (`make back`) 和 worker (`make worker`)
- 浏览器访问 / strategy 自测
```

## 强制约束

- 严格三层（api / services / db），路由不直接查 ORM
- 所有数据库变更必须有 alembic 迁移
- 所有 invoke 走 `src/api/`，不直接 axios
- 所有新 endpoint 必须有冒烟测试
- 不引入新依赖前先问用户
