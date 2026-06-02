# CLAUDE.md — TCAlpha Web Platform

## 语言设置
**必须使用中文**与用户对话。

## 术语约定

| 术语 | 含义 | 对应目录 |
|------|------|---------|
| **后端** | FastAPI + Celery + SQLAlchemy | `backend/app/` |
| **前端** | React 19 UI | `frontend/src/` |
| **API 层** | FastAPI 路由（HTTP 入口） | `backend/app/api/` |
| **Service 层** | 业务逻辑（无 HTTP 知识） | `backend/app/services/` |
| **DB 层** | ORM 模型 + ArcticDB + Redis | `backend/app/db/` |
| **Schema** | Pydantic DTO（请求/响应体） | `backend/app/schemas/` |
| **Task** | Celery 异步任务 | `backend/app/tasks/` |
| **Strategy** | 继承 StrategyBase 的策略类 | `backend/app/strategies/` |
| **Core** | 回测引擎 / 模拟撮合 / Gateway | `backend/app/core/` |

---

## 核心架构（必须牢记）

| 项目 | 规范 |
|------|------|
| **应用类型** | A 股量化分析 + 回测 + 模拟交易 Web 平台 |
| **后端语言** | Python 3.12+（uv 管理） |
| **后端框架** | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic |
| **前端框架** | React 19 + TypeScript 5 + Vite 7 |
| **UI 组件库** | Ant Design 5 + TailwindCSS 4 |
| **状态管理** | Zustand（全局）+ React Hooks（局部）+ React Query（服务端状态） |
| **数据库** | PostgreSQL 16（关系数据）+ ArcticDB（K 线 / Tick 时序） |
| **缓存 / 队列** | Redis 7 + Celery 5（beat + worker） |
| **数据源** | AKShare（A 股免费数据） |
| **策略框架** | VNPY 4.3（仅复用 BarData / TickData / ArrayManager / CtaTemplate） |
| **AI** | OpenAI 兼容 API（DeepSeek / Claude / 智谱 GLM） |
| **部署** | Docker Compose + Nginx + HTTPS |

### 三层架构

```
API 层（router）→ Service 层（业务逻辑）→ DB 层（ORM / ArcticDB / Redis）
```

### 分层职责

| 层级 | 职责 | 关键技术 |
|------|------|---------|
| **API 层** | 路由声明、参数解析、权限校验 | FastAPI router + Depends |
| **Service 层** | 业务逻辑、跨 DB 协调、缓存 | 纯 Python async 函数 |
| **DB 层** | ORM 查询、ArcticDB 读写、Redis 缓存 | SQLAlchemy / ArcticDB / redis |
| **Schema 层** | 请求 / 响应 DTO、数据验证 | Pydantic v2 BaseModel |
| **Task 层** | 异步长任务（下载 / 回测 / 策略） | Celery + Redis broker |
| **Core 层** | 回测撮合引擎、模拟 Gateway | 纯 Python，无 FastAPI 依赖 |
| **前端 API 层** | 统一 axios 调用封装 | `src/api/*.ts` |
| **前端状态层** | 全局共享状态 | Zustand store |
| **前端页面层** | UI 渲染、用户交互 | React 19 + AntD + TailwindCSS |

---

## 目录结构（v0.7.6）

```
tcalpha/
├── backend/
│   ├── run.py                    # ★ dev 启动入口（自动扫端口 + 写 .dev-port）
│   ├── app/
│   │   ├── main.py               # FastAPI 入口 + 路由挂载 + lifespan
│   │   ├── config.py             # ★ 全局配置（Pydantic Settings，读 .env）
│   │   ├── deps.py               # ★ Depends（AsyncSession / current_user_id）
│   │   ├── api/                  # HTTP 入口（仅做路由 + 参数校验 + require_permission）
│   │   │   ├── health.py
│   │   │   ├── auth.py           # /api/auth/* (login/refresh/logout/me)
│   │   │   ├── system.py         # /api/system/* (users/roles/permissions 管理)
│   │   │   ├── market.py         # /api/market/*
│   │   │   ├── strategy.py       # /api/strategy/*
│   │   │   ├── backtest.py       # /api/backtest/*
│   │   │   ├── sim.py            # /api/sim/*（手工下单 + 撤单 + 持仓）
│   │   │   ├── data.py           # /api/data/*
│   │   │   ├── ai.py             # /api/ai/chat（SSE 流式）
│   │   │   ├── ai_chart.py       # /api/ai/chart/analyze（图表 AI）
│   │   │   ├── ai_alerts.py      # /api/ai-alerts/*（AI 盯盘告警）
│   │   │   ├── watchlist.py      # /api/watchlist/*
│   │   │   ├── notify.py         # /api/notify/*（飞书规则）
│   │   │   └── ws.py             # WebSocket 实时行情 / 信号
│   │   ├── services/             # 业务逻辑（无 HTTP 知识）
│   │   │   ├── auth.py           # 密码校验 + JWT 签发 / 旋转 / 黑名单
│   │   │   ├── system.py         # 用户 / 角色 / 权限 CRUD
│   │   │   ├── market.py / strategy.py / backtest.py / sim.py / data.py
│   │   │   ├── ai.py / ai_chart.py / ai_watcher.py / ai_alerts.py
│   │   │   ├── notify.py / feishu.py / watchlist.py / quote.py
│   │   ├── schemas/              # Pydantic v2 DTO
│   │   │   ├── auth.py / system.py / market.py / strategy.py / backtest.py
│   │   │   └── sim.py / ai.py / notify.py / watchlist.py / ai_alert.py
│   │   ├── db/
│   │   │   ├── postgres.py       # ★ AsyncEngine + AsyncSession + Base + SyncSessionLocal
│   │   │   ├── arctic.py         # ★ ArcticDB 单例
│   │   │   ├── redis_client.py
│   │   │   └── models/           # ORM
│   │   │       ├── user.py / role.py / permission.py     # ★ RBAC
│   │   │       ├── strategy.py / backtest.py / order.py / symbol.py
│   │   │       ├── notify.py / watchlist.py / ai_alert.py
│   │   ├── tasks/
│   │   │   ├── celery_app.py     # ★ Celery 实例 + beat_schedule（Asia/Shanghai 时区）
│   │   │   ├── data_tasks.py     # AKShare 数据下载 + 实时报价快照
│   │   │   ├── backtest_tasks.py # 回测异步
│   │   │   ├── strategy_tasks.py # 策略 worker（长跑）
│   │   │   └── ai_tasks.py       # AI 盯盘 beat
│   │   ├── core/                 # 纯 Python，无 FastAPI 依赖
│   │   │   ├── security.py       # ★ bcrypt + JWT + Redis jti 黑名单
│   │   │   ├── auth_deps.py      # ★ AuthUser + get_current_user + require_permission
│   │   │   ├── gateway.py / sim_gateway.py / backtest_engine.py / runtime.py
│   │   │   ├── pubsub.py / event_bus.py
│   │   ├── middleware/
│   │   │   └── basic_auth.py     # v0.6 遗留，默认未挂载（v0.7 起走 JWT）
│   │   ├── workers/
│   │   │   └── notify_dispatcher.py  # 独立进程：订阅 events:* → 飞书
│   │   ├── strategies/
│   │   │   ├── base.py           # ★ StrategyBase（Params / State / Vars 三层 + 实例深拷贝）
│   │   │   └── examples/ma_cross.py
│   │   ├── indicators/           # 技术指标插件
│   │   └── utils/
│   │       ├── logger.py / symbol.py / trading_period.py / rate_limit.py
│   ├── scripts/
│   │   ├── create_admin.py       # 交互式建/重置超管
│   │   ├── seed_symbols.py       # 离线 seed 50 只热门 A 股
│   │   ├── gen_password_hash.py / inject_fake_kline.py / check_pubsub.py
│   ├── tests/
│   │   ├── test_rbac.py / test_system_api.py
│   │   ├── test_backtest_engine.py / test_sim_gateway.py / test_rate_limit.py
│   │   ├── test_ai_watcher.py / test_health.py
│   │   └── conftest.py           # fake_arctic / sample_bars / sync_db fixtures
│   ├── alembic/                  # 数据库迁移
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx              # 入口（<AntApp> + FeedbackBridge + QueryClient + Router）
│   │   ├── App.tsx               # Shell + 路由 + 侧栏按 has(perm) 过滤
│   │   ├── styles/index.css      # TailwindCSS 4 + 工业风全局样式
│   │   ├── api/
│   │   │   ├── client.ts         # ★ Axios 实例 + 401 自动 refresh
│   │   │   ├── auth.ts           # 裸 axios（不走 client）防 401-on-401 死循环
│   │   │   ├── streamClient.ts   # 带刷新的 fetch / SSE 客户端
│   │   │   ├── market.ts / strategy.ts / backtest.ts / sim.ts
│   │   │   ├── ai.ts / ai_chart.ts / notify.ts / watchlist.ts / ai_alerts.ts
│   │   │   └── system.ts         # users / roles / permissions
│   │   ├── components/
│   │   │   ├── PermButton.tsx    # ★ 权限按钮（disabled+Tooltip / hideOnDenied）
│   │   │   ├── FeedbackBridge.tsx
│   │   │   ├── PageScaffold.tsx
│   │   │   └── WorkspaceTabs/
│   │   ├── store/
│   │   │   ├── useAuthStore.ts   # ★ access token + me（has/hasAny/scope 助手）
│   │   │   └── useWorkspaceStore.ts
│   │   ├── hooks/                # useWebSocket / useSSE
│   │   ├── types/index.ts
│   │   ├── utils/feedback.ts
│   │   └── pages/
│   │       ├── Dashboard/ / Chart/ / Strategy/ / Backtest/ / Trade/ / Data/
│   │       ├── AI/ / Notify/ / Login/
│   │       └── System/Users/ + System/Roles/   # ★ 用户/角色管理
│   ├── .dev-port                 # run.py 写入（gitignored）
│   ├── vite.config.ts            # 读 .dev-port 决定代理目标
│   └── package.json
│
├── docs/
│   ├── deploy.md                 # 生产部署（v0.7.x JWT）
│   └── project-bugfix-plan.md    # v0.7.4 修复计划（归档）
├── scripts/start_backend.ps1     # 端口扫描 + uvicorn（PyCharm Run 调它）
├── start-backend.bat / start-frontend.bat
├── .run/                         # ★ PyCharm Run 配置（Backend / Frontend / Celery）
├── docker-compose.yml            # PG + Redis
├── .env.example
└── Makefile
```

---

## 🔴 Skills 强制评估（必须遵守）

> **每次用户提问时，Hook 会注入技能评估提示。必须严格遵循！**

**流程**：
1. **评估**：根据注入的技能列表，列出匹配的技能及理由
2. **激活**：对每个匹配的技能串行调用 `Skill(技能名)`（不可并行）
3. **实现**：所有 Skill() 调用完成后才能开始动手

---

## 🔴 多会话并发自动避让协议（L1/L2/L3 三层触发）

> 用户可能同时开多个 Claude Code 会话操作同一仓库。本会话必须**自动感知并避让**其他会话的工作，**默认静默执行，不打扰用户**。
> 设计原则：宁可绕路，绝不覆盖；宁可静默放弃，绝不擅自 stash / reset / checkout。

### L1 — 启动时探测（首次响应前，仅执行一次）

```bash
git status -s
git branch --show-current
```

- 把"未提交文件清单"和"当前分支"记入会话上下文，整个会话复用，**不向用户复述**
- 若清单非空且与本次任务无关 → 视为"他者占用区"，本会话**不修改、不 stash、不 checkout、不 reset** 这些文件
- 若清单非空且与本次任务相关（用户接续之前的工作）→ 当作己方未完成工作正常处理

### L2 — 修改文件前（按需触发，单文件粒度）

修改任意已存在文件**之前**，执行：

```bash
git log -1 --format="%ar|%s" <file>
```

判定规则（严格按此执行，不询问）：

| 条件 | 处置 |
|------|------|
| 距今 ≥ 15 分钟 | ✅ 自由修改 |
| 距今 < 15 分钟 + 文件**不在** L1 未提交清单 | ✅ 自由修改（已提交的近期改动不冲突） |
| 距今 < 15 分钟 + 文件**在** L1 未提交清单 + 可绕开 | ⚠️ **静默换路径绕开**，不告知用户 |
| 距今 < 15 分钟 + 文件**在** L1 未提交清单 + 必须改同文件 | 🛑 **此时唯一允许打扰用户一次**："`<file>` 15min 内有未提交改动，疑似其他会话占用，是否继续？" |

### L3 — 提交前（强校验，必做）

`git commit` 前：

```bash
git diff --cached --name-only
```

- 对照本会话明确改过的文件清单（自维护）
- 越界文件 → **静默 `git restore --staged <file>`**，仅提交本会话范围内文件
- 逐个 `git add <具体文件>`，**禁止** `git add -A` / `git add .`

### 跨会话操作禁令（不询问、直接禁止）

| 禁令 | 原因 |
|------|------|
| ❌ `git stash` / `git stash pop` | 会污染其他会话的工作区 |
| ❌ `git reset --hard` | 会丢其他会话的未提交改动 |
| ❌ `git checkout <file>`（丢弃改动） | 同上 |
| ❌ `git checkout <branch>`（切分支） | 除非用户明确指示 |
| ❌ `git add -A` / `git add .` | 可能误提交他者文件，必须逐个 add |
| ❌ `git clean -fd` | 会删他者未跟踪文件 |
| ❌ kill 端口 / `taskkill /F` 进程 | 他者 dev server 可能在用 |

---

## ⚠️ 开发强制要求

**开发前必须：先读参考代码 → 了解现有模式 → 按相同风格编写**

### 参考代码位置

| 开发类型 | 参考代码 |
|---------|---------|
| **FastAPI 路由** | `backend/app/api/health.py`（最简洁）、`backend/app/api/market.py` |
| **Service 函数** | `backend/app/services/market.py` |
| **Pydantic Schema** | `backend/app/schemas/market.py` |
| **ORM 模型** | `backend/app/db/models/user.py`、`strategy.py` |
| **Celery 任务** | `backend/app/tasks/data_tasks.py` |
| **ArcticDB 操作** | `backend/app/db/arctic.py` |
| **策略类** | `backend/app/strategies/examples/ma_cross.py` |
| **前端页面组件** | `frontend/src/pages/Dashboard/index.tsx` |
| **前端 API 封装** | `frontend/src/api/market.ts` |
| **前端 Axios 客户端** | `frontend/src/api/client.ts` |
| **前端类型定义** | `frontend/src/types/index.ts` |

---

## 🔴 绝对禁止的写法

> ⚠️ Shell：别 `cd <子目录> && <命令>`——Bash 会话 cwd 持久，会让 Claude Code statusline 项目名飘到子目录。用 `uv --directory backend run ...` / `git -C` / `pnpm --dir frontend ...` 代替。

### Python 后端

| 错误做法 | 正确做法 | 原因 |
|---------|---------|------|
| `os.environ.get("KEY")` | `from app.config import settings; settings.key` | 配置必须集中管理 |
| 在 router 里写业务逻辑 | 业务逻辑挪到 `services/` | 保持三层架构分离 |
| 同步 SQLAlchemy `Session` | 异步 `AsyncSession` + `await` | 整个栈全异步 |
| 裸 `print()` 调试 | `from loguru import logger; logger.info(...)` | 统一日志格式 |
| `async def` 函数里 `time.sleep()` | `await asyncio.sleep()` | 阻塞事件循环 |
| ArcticDB 在 router 里直接读 | Service 层读，必要时加 Redis 缓存 | 大数据不走 HTTP 线程 |
| Alembic 修改已合并的迁移文件 | 写新迁移（autogenerate 或手写） | 破坏迁移历史 |
| Celery task 里做 HTTP 请求不限流 | 使用 `utils/` 里的限流工具 | AKShare 有速率限制 |

### TypeScript 前端

| 错误做法 | 正确做法 | 原因 |
|---------|---------|------|
| 组件里裸写 `axios.get(...)` | 封装到 `src/api/*.ts` | 统一管理、便于 mock |
| 跨页面 props 透传共享状态 | 提到 Zustand store | React 推荐模式 |
| `any` 类型 | 定义明确的 TypeScript 接口 | strict 模式要求 |
| 使用 `class` 组件 | 函数组件 + Hooks（ErrorBoundary 除外） | React 19 推荐模式 |
| 不用 Ant Design 组件 | 优先使用 antd（Table/Card/Form 等） | 统一 UI 风格 |
| 不用 `@/` 路径别名 | `import { X } from "@/types"` | Vite 已配置别名 |
| `useEffect` 里直接 fetch | 用 `useQuery` 管理服务端状态 | 自动处理 loading/error/cache |

---

## 新功能开发标准流程

### 新增一个 API 功能（全栈）

```
1. db/models/<x>.py        定义 ORM 模型 + 在 __init__.py 导出
2. alembic revision …      autogenerate 生成迁移 → upgrade head
3. schemas/<x>.py          定义请求 / 响应 DTO（Pydantic v2）
4. services/<x>.py         实现业务逻辑（async，调 DB / ArcticDB）
5. api/<x>.py              实现路由（调 Service，返回 DTO）
6. main.py                 include_router 挂载
─────
7. frontend/src/types/index.ts  对应 TypeScript 接口
8. frontend/src/api/<x>.ts      封装 axios 调用
9. frontend/src/pages/<X>/      页面组件（useQuery + AntD）
10. App.tsx                     加 Route + 侧栏菜单项
```

### 新增 Celery 任务

```
1. tasks/<name>_tasks.py   @celery_app.task 实现
2. tasks/celery_app.py     include_tasks 加入模块 + beat_schedule 配 cron
```

### 新增策略

```
1. strategies/examples/<name>.py  继承 StrategyBase，定义 Params/State/on_bar
2. services/strategy.py            加载 / 实例化策略的逻辑
3. tasks/strategy_tasks.py         异步运行任务
```

---

## 命名规范

| 维度 | 规范 | 示例 |
|------|------|------|
| Python 模块 / 变量 / 函数 | snake_case | `market_service.py`、`get_kline()` |
| Python 类 | PascalCase | `MarketService`、`KlineSchema` |
| FastAPI router | 小写复数路径 | `/api/market/symbols` |
| Celery task | snake_case 函数名 | `@celery_app.task` `def download_daily_kline()` |
| TypeScript 接口 | PascalCase + `I` 前缀可选 | `KlineBar`、`StrategyConfig` |
| TypeScript 函数 | camelCase | `fetchSymbols()`、`useKlineQuery()` |
| React 组件文件 | PascalCase 目录 + `index.tsx` | `pages/Dashboard/index.tsx` |
| Zustand store 文件 | camelCase + `Store` | `src/store/auth.ts` |

---

## 前端核心规范（src/）

### 技术栈

| 技术 | 用途 | 导入方式 |
|------|------|---------|
| **Ant Design 5** | UI 组件库 | `import { Button, Table } from "antd"` |
| **TailwindCSS 4** | 原子化布局样式 | `className="flex items-center gap-2"` |
| **Zustand** | 全局状态 | `import { useAuthStore } from "@/store/auth"` |
| **React Query** | 服务端状态 / 缓存 | `import { useQuery } from "@tanstack/react-query"` |
| **ECharts** | 通用图表 | `import * as echarts from "echarts"` |
| **lightweight-charts** | 高性能 K 线 | `import { createChart } from "lightweight-charts"` |
| **Axios** | HTTP 客户端 | 封装在 `@/api/client.ts`，禁止裸用 |

### 页面组件开发模式

```tsx
// ─── src/pages/Data/index.tsx ───
import { Card, Table } from "antd"
import { useQuery } from "@tanstack/react-query"
import { fetchSymbols } from "@/api/market"
import type { Symbol } from "@/types"

export default function DataPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 30_000,
  })

  return (
    <div className="p-6">
      <Card title="股票列表">
        <Table<Symbol>
          dataSource={data}
          loading={isLoading}
          rowKey="code"
        />
      </Card>
    </div>
  )
}
```

### API 封装模式

```typescript
// ─── src/api/market.ts ───
import { client } from "./client"
import type { Symbol, KlineBar } from "@/types"

export const fetchSymbols = () =>
  client.get<Symbol[]>("/api/market/symbols").then((r) => r.data)

export const fetchKline = (code: string, period: string) =>
  client.get<KlineBar[]>(`/api/market/kline/${code}`, { params: { period } })
    .then((r) => r.data)
```

### 状态管理选择

| 场景 | 方案 |
|------|------|
| 组件内短暂状态 | `useState` |
| 服务端数据（列表 / 详情） | `useQuery`（React Query） |
| 服务端写操作 | `useMutation`（React Query） |
| 全局 UI 状态（主题 / 用户 / 侧栏） | Zustand store |
| 当前登录态 / 权限判断 | `useAuthStore`（`accessToken` / `me` / `has(perm)` / `scope()`） |

### 写按钮加权限守卫（v0.7.6+）

```tsx
import { PermButton } from "@/components/PermButton"

<PermButton perm="strategy.write" type="primary" onClick={openCreate}>
  新建策略
</PermButton>

// 纯破坏性操作（删除）用 hideOnDenied 彻底隐藏
<PermButton perm="strategy.delete" hideOnDenied danger onClick={confirm}>
  删除
</PermButton>
```

- super 用户自动绕过（`useAuthStore.has` 处理）
- 默认 disabled + Tooltip 提示"需要权限：xxx"，让 viewer 知道功能存在
- 真正的安全边界是后端 `require_permission(...)`，前端只是 UX

---

## 常见错误速查

### 后端

| ❌ 错误写法 | ✅ 正确写法 |
|---------|---------|
| router 里写 SQL | 挪到 `services/` → `db/` |
| 同步 `Session` | `AsyncSession` + `await` |
| 直接 `os.environ.get` | `settings.xxx` |
| ArcticDB 写在 router | Service 层 + Redis 缓存 |
| 忘记在 `main.py` 挂载 router | `app.include_router(x.router, prefix=...)` |
| Celery task 不加 `bind=True` 就用 `self.retry` | `@celery_app.task(bind=True)` |
| 修改已 merge 的 alembic 迁移 | 写新迁移文件 |

### 前端

| ❌ 错误写法 | ✅ 正确写法 |
|---------|---------|
| 组件里裸写 `axios.get` | 封装到 `src/api/*.ts` |
| props 层层传共享状态 | Zustand store |
| `useEffect` + `fetch` 管理服务端数据 | `useQuery` |
| 不用 `@/` 别名 | `import { X } from "@/types"` |
| `any` 类型 | 明确的 TypeScript 接口 |

---

## 构建与运行（v0.7.6）

### 启动后端（4 选 1，本质都是跑 `backend/run.py`）

| 方式 | 命令 / 操作 |
|------|-------------|
| **PyCharm Run（推荐）** | 顶栏 ▶「Backend (run.py)」 |
| 资源管理器双击 | `start-backend.bat`（Windows） |
| Makefile | `make back-safe` |
| 裸 Python | `uv --directory backend run python run.py` |

`run.py` 会自动 `socket.bind()` 从 8000..8049 找一个真正可用的端口（绕开 Windows tcpip.sys socket 泄漏），把端口写到 `frontend/.dev-port`；vite 启动时读这个文件决定代理目标，前后端永远自动对齐。

### 快捷命令（Makefile）

```bash
make up          # 起 PG + Redis (docker compose up -d)
make down        # 停依赖服务
make back-safe   # 起 FastAPI（动态端口 + 热重载）
make worker      # 起 Celery worker（跑回测 / 数据下载 / AI 盯盘需要）
make beat        # 起 Celery beat（定时任务）
make notify      # 起飞书通知分发 worker
make front       # 起 Vite 前端 (localhost:5173)
make migrate     # alembic upgrade head
make revision m="消息"  # 生成新迁移
make test        # pytest
make fmt         # ruff format
make lint        # ruff check + mypy
```

### 不走 Makefile 的命令（不要 cd）

```bash
# 后端（uv）
uv --directory backend run python run.py        # 推荐入口
uv --directory backend run pytest tests/
uv --directory backend run alembic upgrade head
uv --directory backend run python scripts/create_admin.py   # 建超管
uv --directory backend run python scripts/seed_symbols.py   # seed 50 只热门股

# 前端（pnpm）
pnpm --dir frontend dev
pnpm --dir frontend build
pnpm --dir frontend exec tsc --noEmit
```

### 开发地址

| 服务 | 地址 | 说明 |
|------|------|------|
| FastAPI 后端 | `http://127.0.0.1:<port>` | `<port>` 由 `frontend/.dev-port` 决定（run.py 启动时打印） |
| FastAPI Docs | `http://127.0.0.1:<port>/docs` | Swagger UI（需 Bearer token 才能调业务接口） |
| Vite 前端 | `http://localhost:5173` | 浏览器入口；/api 自动代理到后端 |

---

## 快速命令（/slash）

| 命令 | 用途 |
|------|------|
| `/start` | 新窗口快速了解项目背景和进度 |
| `/dev` | 开发新功能（三层架构全栈代码生成） |
| `/api` | 快速新增 FastAPI endpoint |
| `/strategy` | 新增或调试策略类 |
| `/backtest` | 回测任务相关开发 |
| `/check` | 代码规范检查（ruff + mypy + tsc） |
| `/progress` | 项目进度报告（Phase 当前状态） |
| `/release` | 发布新版本（commit + push 双远程） |

---

## 🔴 开发前检查清单

- [ ] **已读参考代码** — `backend/app/api/*.py` 和 `frontend/src/pages/*/index.tsx`
- [ ] **遵循三层架构** — router → service → db，禁止跨层
- [ ] **使用 AsyncSession** — 所有 ORM 操作异步
- [ ] **使用 Pydantic Schema** — 请求 / 响应有 DTO，不裸传 dict
- [ ] **使用 Ant Design** — UI 组件优先用 antd
- [ ] **API 封装到 src/api/** — 禁止在组件里裸写 axios
- [ ] **服务端状态用 React Query** — useQuery / useMutation
- [ ] **使用 @/ 别名** — 禁止相对路径跨多层
- [ ] **类型对齐** — Python Schema 和 TypeScript 接口保持一致
- [ ] **不违反禁止项** — 检查上方禁止表格
- [ ] **不走 cd** — 用 `uv --directory` / `pnpm --dir` / `git -C`
