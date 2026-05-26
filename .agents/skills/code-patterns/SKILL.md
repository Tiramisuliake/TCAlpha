---
name: code-patterns
description: TCAlpha 编码规范（Python + TypeScript + React）。触发词：规范、命名、编码、Python 规范、TypeScript 规范、代码风格、最佳实践、重构
---

# 编码规范

## Python（backend/）

### 命名

| 类型 | 规范 | 示例 |
|---|---|---|
| 文件 / 模块 | snake_case | `data_tasks.py` |
| 类 | PascalCase | `BacktestEngine` |
| 函数 / 变量 | snake_case | `get_kline()` |
| 常量 | UPPER_SNAKE | `DEFAULT_USER_ID` |
| 私有 | `_lead_underscore` | `_engine` |

### 必须

- Python 3.13，所有函数必须有 type hints
- `from __future__ import annotations`（除非用 Pydantic v2 model 需要运行时类型）
- Pydantic v2 模型用 `model_config = ConfigDict(...)`
- 日志统一 loguru，禁用 `print` 和 `logging.getLogger`
- 配置只走 `from app.config import settings`，禁止 `os.environ.get`
- DB session 只走 `Depends(get_db)`，禁止全局 session
- 异步 DB 操作用 `async/await + AsyncSession`，同步只在 alembic / celery worker 中允许
- SQL 写在 ORM 里，禁止字符串拼 SQL 防注入
- 时间统一 `Asia/Shanghai`（用 `pytz`），DB 字段都用 `DateTime(timezone=True)`

### 禁止

- 顶层 `from x import *`
- 在 endpoint 里直接调 AKShare / OpenAI（必须通过 service 或 Celery）
- Bare `except:`（必须 `except (XxxError, YyyError):` 或捕获后重新 raise）
- print 调试代码留在提交中

### Import 顺序（ruff/isort 自动处理）

1. 标准库
2. 第三方
3. `app.*` 本项目
4. 相对 import（少用，只在同子包内）

## TypeScript / React（frontend/）

### 命名

| 类型 | 规范 | 示例 |
|---|---|---|
| 组件文件 | PascalCase 目录 + `index.tsx` | `pages/Dashboard/index.tsx` |
| Hook | `use<X>` | `useWebSocket.ts` |
| Store | `use<X>` | `store/useAuth.ts` |
| 类型 | PascalCase | `interface Bar { ... }` |
| 常量 | UPPER_SNAKE 或 camelCase | `MAX_KLINE_LIMIT` |

### 必须

- TS strict 模式，禁用 `any`（不得已用 `unknown` 再缩窄）
- 函数组件 + Hooks，禁用 class 组件
- 路径用 `@/` 别名（vite + tsconfig 已配）
- 服务器状态用 React Query（`useQuery` / `useMutation`），UI 状态用 Zustand
- API 调用统一在 `src/api/*.ts`，组件里不能直接 `axios.get`
- UI 优先 AntD，布局用 Tailwind utility class
- 表单用 AntD Form + rules，删除/不可逆操作必须 `Modal.confirm`
- WebSocket / SSE 走自定义 hook（`useWebSocket` / `useSSE`），带重连

### 禁止

- 直接 fetch 第三方 API（AKShare / OpenAI），必须走后端代理
- 内联 style（除动态计算外，统一 Tailwind class）
- 把 token 存 localStorage 不加密
- export default 一个匿名箭头函数（不好调试）

## 工具

```bash
# 后端
ruff format .          # 格式化
ruff check . --fix     # lint
mypy app               # 类型检查
pytest                 # 测试

# 前端
pnpm typecheck
pnpm lint
```

## 提交前 checklist

- [ ] `ruff check . && mypy app` 后端通过
- [ ] `pnpm typecheck` 前端通过
- [ ] 新增 endpoint 有对应测试
- [ ] 新增数据库字段有 alembic 迁移
- [ ] 没有 print / console.log 残留
- [ ] 没有写死密码 / API Key
