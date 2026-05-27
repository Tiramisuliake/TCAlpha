# Changelog

## [Unreleased]

## [0.6.0] — 2026-05-27

### Added — Phase 6 Step 1：Basic Auth 鉴权

公网部署的前置必备：让 TCAlpha 不再 "0 鉴权裸奔"。

后端：
- `config.py` 新增 `auth_enabled` / `auth_username` / `auth_password_hash` / `auth_public_paths` / `auth_protect_docs`
- `middleware/basic_auth.py`：ASGI 中间件，同时覆盖 HTTP + WebSocket
  - HTTP 路径走标准 `Authorization: Basic <base64>` header
  - WebSocket 不能传 header，回退到 `?token=base64(user:pass)` 查询参数
  - 公共白名单走 `auth_public_paths`（默认 `/health` `/`），`/docs` 等元数据由 `auth_protect_docs` 控制
  - bcrypt 5.x 直接对接（绕过 passlib 4.x 自检兼容 bug，安全截断到 72 字节）
- `main.py`：按 `settings.auth_enabled` 开关挂载 `BasicAuthMiddleware`
- `scripts/gen_password_hash.py`：bcrypt 密码哈希生成工具

前端：
- `store/useAuthStore.ts`：Zustand store + sessionStorage 凭证（关 tab 即失效），导出 `authHeader()` / `wsUrl()` 工具
- `api/client.ts`：axios 请求拦截器自动注入 `Authorization`；响应拦截器收到 401 时清状态并跳 `/login`
- `api/ai.ts::streamChat`：SSE-over-fetch 同样带 Auth header
- `pages/Strategy/index.tsx`：WS 改走 `wsUrl()`，移除硬编码 `ws://localhost:8000`
- `pages/Login/index.tsx`：新增登录页（用户名 + 密码，自带探活校验）
- `App.tsx`：`RequireAuth` 路由守卫，未登录访问任意页面跳 `/login?from=<path>`

### Added — Phase 5 Step 4：图表 AI 分析

- `services/ai_chart.py` + `api/ai_chart.py`：`GET /api/ai/chart/analyze?symbol=&period=` SSE 流式
- `frontend/src/api/ai_chart.ts::streamChartAnalysis`：GET fetch + SSE 解析，复用 `authHeader()`
- `pages/Chart/index.tsx`：右上"AI 分析"按钮 → 抽屉打开 → 喂当前 symbol/period 给 AI 流式解读

### 工具 / 文档

- `.env.prod.example`：生产环境完整 `.env` 模板
- `docs/deploy.md`：从 0 到 v0.6.0 的部署 runbook + 安全自检

## [0.5.2] — 2026-05-27

### Added — Phase 5 Step 3 AI 盯盘

后端：
- `db/models/watchlist.py` + `ai_alert.py`：用户关注列表（user_id+symbol 唯一约束）+ AI 盯盘告警结果（含指标快照）
- 迁移 `3b597a00cb62_add_watchlists_and_ai_alerts`，server_default 兼容空表
- `services/ai_watcher.py`：核心盯盘函数
  - `build_snapshot(symbol)`：读 ArcticDB `bar_1d` 最近 60 根，算 MA5/10/20 / RSI14 / MACD（DIF/DEA/HIST 自实现 EMA）/ 5d & 20d 涨跌幅 / 量能比
  - `watch_symbol(user_id, symbol)`：拼 prompt → DeepSeek `response_format={"type":"json_object"}` 单次调用 → Pydantic `WatchResult` 严格校验 → 落 `ai_alerts` → `publish_event("ai.alert.{level}")`
  - 系统 prompt 严格要求 level/signal/reason 三字段 JSON，禁止"建议买入"等投资建议措辞
- `tasks/ai_tasks.py`：
  - `ai_watch_all`（beat 触发，遍历所有 watchlist，可 `force=True` 跳过交易时段判断）
  - `ai_watch_one`（手动单标的）
  - `celery_app.py` beat 加 `crontab(minute='*/15', hour='9-14')`
- `api/watchlist.py` + `api/ai_alerts.py`：watchlist CRUD + alert 列表（level/symbol/only_unacked 过滤）+ ack + 手动触发 `POST /api/ai-alerts/watch/{symbol}`
- 集成：盯盘结果走 `ai.alert.warn` / `ai.alert.danger` 事件，用户在「通知中心」勾 `ai.alert.*` 即可推送到飞书

前端：
- `api/watchlist.ts` + `api/ai_alerts.ts`：API 封装
- `pages/AI/index.tsx` 改造为 Tabs：
  - **助手聊天**：保留原 chat（拆为 `Chat.tsx`）
  - **AI 盯盘**：告警卡片列表（level 段选 / 未读切换 / ack 按钮 / 折叠指标快照）
  - **关注列表**：股票增删 + 行内"盯一次"手动触发 + "查告警"跳转

工具：
- 无新外部依赖

## [0.5.1] — 2026-05-27

### Added — Phase 5 Step 2 通知中心 + 飞书推送

后端：
- `db/models/notify.py`：`NotifyRule` / `NotifyLog` 表（用户级飞书 webhook + 签名密钥 + 静音时段）
- `alembic/versions/a332786c9ac0_add_notify_rules_and_logs.py`：迁移（含 server_default 兼容空表）
- `core/event_bus.py`：统一事件总线 `publish_event(type, payload, level, user_id)`，底层 Redis pub/sub `events:*` 通道，命名 `category.action.subaction`
- `services/feishu.py`：`send_card` / `send_text`，HMAC-SHA256 签名 + Redis 令牌桶限流（100/min/webhook）+ httpx async
- `services/notify.py` / `schemas/notify.py` / `api/notify.py`：规则 CRUD + 历史查询 + 测试推送 + 事件类型 / 渠道元数据接口
- `workers/notify_dispatcher.py`：独立进程，`asyncio` psubscribe `events:*`，按 NotifyRule 通配匹配 + quiet_hours 过滤 + 30s SETNX 去重，分发到飞书并落 NotifyLog
- 业务接入：`runtime.py` 发出 `strategy.started/stopped/crashed`、`backtest_tasks` 发 `backtest.started/done/failed`、`main.py` 全局 exception handler 发 `api.exception`

前端：
- `api/notify.ts`：规则 / 历史 / 元数据 / 测试推送 API 封装
- `pages/Notify/index.tsx`：规则 + 历史 双 tab UI，规则 Drawer（事件类型多选 + 通配符 + 渠道 + webhook + 签名 + 静音时段 + 启用开关），逐行"测试"按钮 + 顶部"临时测试"弹窗
- `App.tsx` / `useWorkspaceStore.ts` / `WorkspaceTabs`：加路由 `/notify` + 侧栏菜单项 + tab 图标

工具：
- `Makefile`：`make notify` = `uv run python -m app.workers.notify_dispatcher`
- `.env.example`：飞书全局兜底占位（实际 webhook 走 PG，每用户独立）

## [0.5.0] — 2026-05-27

### Added — Phase 5 AI 助手（Step 1 / chat MVP）
- `backend/app/schemas/ai.py`：`ChatMessage` / `ChatRequest` DTO（多轮历史 + 可选 system + temperature）。
- `backend/app/services/ai.py`：OpenAI 兼容 `AsyncOpenAI` 单例 + `stream_chat()` 异步生成器，默认 DeepSeek（`AI_API_BASE` / `AI_API_KEY` / `AI_MODEL` 走 `.env`）。
- `backend/app/api/ai.py`：`POST /api/ai/chat` 改为真实 SSE 流式（替换 Phase 0 的 echo 占位），协议 `data: <chunk-json>` / `[DONE]` / `[ERROR]<msg>`。
- `frontend/src/api/ai.ts`：浏览器 SSE-over-fetch 客户端（EventSource 不支持 POST，故用 `ReadableStream` 自己拆 `data:` 帧），支持 `AbortController` 取消。
- `frontend/src/pages/AI/index.tsx`：气泡式聊天 UI — 流式打字效果、停止按钮、清空对话、Enter 发送 / Shift+Enter 换行、自动滚到底部。

### Added — 前端工作台升级
- `frontend/src/components/WorkspaceTabs`：多标签切换组件（基于 `@dnd-kit` 支持拖拽排序）。
- `frontend/src/components/PageScaffold.tsx`：统一的 flex 页面骨架组件，所有 page 复用。
- `frontend/src/store/useWorkspaceStore.ts`：Zustand 全局 workspace 状态（activeKey + 标签集合）。
- `frontend/src/main.tsx`：AntD 5 自定义主题 token（Layout / Menu / Card / Table / Button），统一圆角 8、控件高 36、表格 hover bg。
- 各 page（Dashboard / Chart / Strategy / Backtest / Data / AI）改造为 `PageScaffold` 子节点，统一外边距与高度。

### Changed
- `frontend/tsconfig.json`：移除 `references → tsconfig.node.json`，改 `include: ["src", "vite.config.ts"]` + `types: ["node"]`，修复编译路径。删除冗余的 `tsconfig.node.json`。
- `frontend/package.json`：`build` / `typecheck` 改为 `tsc --noEmit`（不再 emit 产物，避免污染工作树）。

### Chore
- 入仓 `.agents/` / `.codex/` / `AGENTS.md`：Codex 协作工具的共享 skills / hooks 配置，与 `.claude/` 同等待遇。

## [0.4.2] — 2026-05-26

### Fixed
- **Bug B** — `core/runtime.py::StrategyRuntime.run`：策略 task 异常退出时未清理 `strategy:running:{id}` Redis key，下次启动卡在 "strategy already running"。改为 try/finally 包住主循环，finally 中 `delete(running_key) + delete(stop_key)` 并把 DB status 写成 `stopped`/`error`。
- **Bug C** — `users` / `symbols` 表 schema 与 ORM 漂移：早期 `User` 模型加了 `password_hash` / `is_active` 但缺迁移；`select(User)` 报 `UndefinedColumn`。新增迁移 `27f8f3ac68c7_sync_users_and_symbols_schema`，补齐两列（`server_default` 兼容已有行）并把 `users` / `symbols` 的唯一约束统一为唯一索引。
- **Bug D** — `/health` 与根路径 `/`、`FastAPI(version=...)` 都硬编码 `0.1.0`。改为在 `app/__init__.py` 用 `tomllib` 读 `pyproject.toml`，三处统一引用 `app.__version__`。

### Added (chore)
- `backend/app/main.py` 末尾加 `if __name__ == "__main__": uvicorn.run(...)` 入口，PyCharm 右键 Run 即可启动后端（无需自配 module 命令）。

## [0.4.1] — 2026-05-26

### Fixed
- `core/backtest_engine.py::_load_bars`：naive `pd.Timestamp` 与 tz-aware `DatetimeIndex` 比较抛 `TypeError`，导致实时策略 worker 启动后立刻 crash、回测引擎读 ArcticDB 也受同一 bug 影响。改为按 index 的 `tz` 自动构造对齐的 start/end Timestamp。

### Added
- `backend/scripts/inject_fake_kline.py`：联调专用，向 ArcticDB `bar_1d` 灌 200 根带金叉/死叉走势的合成日 K（金叉位于约 60-120 根处，死叉位于 180+），用于无网络环境下的策略 / 回测路径快速验证。
- `backend/scripts/ws_listener.py`：联调专用 WebSocket 客户端，同时订阅 `/ws/orders` + `/ws/signals` 把消息打 stdout，方便观察 `SimGateway` → Redis pub/sub → WS 推送链路。

## [0.4.0] — 2026-05-26

### Added
- Phase 4：实时策略 worker + 模拟撮合
  - Alembic 迁移 `3b8d5e2a7c19`：`sim_orders` 表
  - `core/pubsub.py`：Redis channel 命名约定 + 同步发布工具
  - `core/sim_gateway.py`：`SimGateway`（`send_order` / `match` / `cancel` / `position`），按下一根 bar 开盘价撮合，结果发 Redis pub/sub
  - `core/runtime.py`：`StrategyRuntime`（ArcticDB 历史热身 → 循环驱动 `on_bar` → 下单），Redis stop key 优雅退出
  - `tasks/strategy_tasks.py`：`run_strategy` Celery 长跑任务（24h `time_limit`）
  - `api/ws.py`：`/ws/orders`、`/ws/signals`、`/ws/quote`（Redis pub/sub → WebSocket 转发）
  - `api/strategy.py`：新增 `start` / `stop` / `running` 端点
  - `api/sim.py` + `services/sim.py`：订单列表、持仓聚合
- 前端
  - `hooks/useWebSocket.ts`：自动重连 WebSocket hook
  - `api/sim.ts`：模拟交易 API 封装
  - Strategy 页面重构：策略列表 + 选中面板（启停按钮 + 信号卡 + 实时订单），WebSocket 订阅 `/ws/orders` + `/ws/signals` 实时更新

## [0.3.0] — 2026-05-26

### Added
- Phase 3：策略管理 + 回测引擎（Celery 异步）
  - Alembic 迁移 `2a4f7c91e035`：`users` / `strategy_configs` / `backtest_jobs` / `backtest_trades` 表
  - `core/backtest_engine.py`：`BacktestEngine`（ArcticDB 读取 → `on_bar` 撮合 → 指标计算 → 落 PG）
  - `strategies/examples/ma_cross.py`：`MaCrossStrategy` 完整 `on_bar`（金叉开多 / 死叉平多）
  - `tasks/backtest_tasks.py`：`run_backtest` Celery 异步任务（1h `time_limit`）
  - `services/strategy.py`：策略 CRUD + 策略类注册表
  - `services/backtest.py`：提交 / 状态 / 成交明细查询
  - `api/strategy.py` & `api/backtest.py`：完整 REST 路由
- 前端
  - `api/strategy.ts` + `api/backtest.ts` 封装
  - Strategy 页面：策略列表 + 新建 / 编辑 Drawer + 参数配置
  - Backtest 页面：提交表单 + 状态轮询 + 资金曲线（ECharts）+ 指标卡 + 成交明细

### Fixed
- `@tailwindcss/postcss` 依赖缺失

## [0.2.0] — 2026-05-26

### Added
- Phase 2：前端布局 + K 线图
  - App Shell：侧边栏导航 + 路由（仪表盘 / K 线 / 策略 / 回测 / 数据 / AI）
  - Chart 页面：lightweight-charts K 线主图 + 成交量副图 + 周期切换 + 股票搜索
  - Data 页面：股票列表表格（搜索 / 交易所过滤 / 分页）+ 一键刷新 + 单股 K 线下载触发
  - Dashboard：后端状态卡 + 股票数量统计
  - `POST /api/market/symbols/refresh` 触发全市场股票列表刷新 Celery 任务

### Fixed
- `deps.py` 模块级绑定导致 `async_session_factory` 为 None 的启动 bug
- Vite 代理补全 `/health` 路径

## [0.1.0] — 2026-05-26

### Added
- Phase 0：项目骨架（FastAPI + Celery + SQLAlchemy + ArcticDB + React + Docker）
- Phase 1：数据层
  - `Symbol` ORM 模型（symbols 表）
  - AKShare 日 K 下载（限流令牌 + tenacity 重试 + ArcticDB 增量落库）
  - Celery 任务：`refresh_symbol_list` / `download_one_symbol` / `download_daily_kline_all`
  - market API：`GET /api/market/symbols` / `GET /api/market/kline/{symbol}` / `POST /api/market/kline/{symbol}/download`
  - CLAUDE.md 项目规范文档
