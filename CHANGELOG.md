# Changelog

## [Unreleased]

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
