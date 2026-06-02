# Plan: TCAlpha 项目 Bug 修复与启动稳定化

> 📦 **归档**：本计划已在 **v0.7.4 ~ v0.7.6** 全部落地实施。完整修复清单见 `CHANGELOG.md`。
> 保留本文件作为修复决策的历史参考。

**Generated**: 2026-05-30
**Implemented**: 2026-06-02（v0.7.4 主体 + v0.7.6 后续补丁）
**Estimated Complexity**: Medium

## Overview

目标是把当前项目从“能构建但质量门禁不稳”推进到“可稳定启动、核心测试通过、主要权限风险收敛”。优先级按影响排序：启动/迁移阻断、确定性业务 bug、鉴权安全缺口、测试稳定性、静态检查与开发体验。

## Prerequisites

- 本地 PostgreSQL 和 Redis 可用：`docker compose up -d`
- 后端依赖已同步：`uv --directory backend sync`
- 前端依赖已安装：`pnpm --dir frontend install`
- 不修改他人未提交文件；提交前只逐个 stage 本计划内文件

## Sprint 1: 启动与数据库基线

**Goal**: 让本地环境处于可运行、迁移版本一致的状态。

**Demo/Validation**:
- `uv --directory backend run alembic current` 显示最新 head
- `uv --directory backend run pytest tests/test_health.py -q` 可执行
- 浏览器能打开 `http://localhost:5173/`

### Task 1.1: 应用缺失迁移
- **Location**: `backend/alembic/versions/b1c2d3e4f5a6_add_sim_order_place_permission.py`
- **Description**: 执行 `uv --directory backend run alembic upgrade head`，让本地 DB 从 `7aaf2f5c947e` 升到 `b1c2d3e4f5a6`。
- **Dependencies**: 无
- **Acceptance Criteria**:
  - `alembic current` 等于 `b1c2d3e4f5a6`
  - `permissions` 存在 `sim.order.place`
- **Validation**:
  - `uv --directory backend run alembic current`

### Task 1.2: 验证启动链路
- **Location**: `backend/run.py`, `frontend/vite.config.ts`
- **Description**: 用动态端口启动后端，再启动 Vite，确认前端代理读到 `frontend/.dev-port`。
- **Dependencies**: Task 1.1
- **Acceptance Criteria**:
  - 后端输出 API 地址
  - 前端访问 `/health` 能代理到后端
- **Validation**:
  - `uv --directory backend run python run.py`
  - `pnpm --dir frontend dev`

## Sprint 2: 修复确定性业务 Bug

**Goal**: 修复已由测试复现的股票代码归一化问题。

**Demo/Validation**:
- `normalize("600000.SH") == "sh600000"`
- `normalize("000001.SZ") == "sz000001"`
- `normalize("430047.BJ") == "bj430047"`

### Task 2.1: 修复后缀格式股票代码解析
- **Location**: `backend/app/utils/symbol.py`
- **Description**: 在 `normalize()` 中先识别 `600000.SH` / `000001.SZ` / `430047.BJ` 这类后缀格式，再进入现有前缀/纯数字逻辑。
- **Dependencies**: Sprint 1
- **Acceptance Criteria**:
  - 保持 `sh.600000`, `600000`, `sh600000` 等现有格式兼容
  - 未知交易所后缀继续抛 `ValueError`
- **Validation**:
  - `uv --directory backend run pytest tests/test_health.py::test_symbol_normalize -q`

### Task 2.2: 补充覆盖用例
- **Location**: `backend/tests/test_health.py`
- **Description**: 增加 `.SZ`、`.BJ`、小写后缀和非法后缀用例。
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - 交易所后缀大小写不敏感
  - 非法格式仍失败
- **Validation**:
  - `uv --directory backend run pytest tests/test_health.py -q`

## Sprint 3: WebSocket 鉴权加固

**Goal**: 防止订单和策略信号 WebSocket 被任意 user_id 或 strategy_id 越权订阅。

**Demo/Validation**:
- 未登录连接订单 WS 被拒绝
- 普通用户不能订阅其他用户订单频道
- 用户只能订阅自己拥有的策略信号

### Task 3.1: 设计 WebSocket JWT 解析工具
- **Location**: `backend/app/api/ws.py`, `backend/app/core/auth_deps.py` 或新建 `backend/app/core/ws_auth.py`
- **Description**: 从 `Authorization` 不可用的浏览器 WS 场景中读取 `?token=`，复用 `decode_token()` 获取当前用户。
- **Dependencies**: Sprint 1
- **Acceptance Criteria**:
  - token 缺失/过期/类型错误时关闭连接
  - 不破坏现有前端 `wsUrl()` 拼 token 的行为
- **Validation**:
  - 新增后端 WS 鉴权单测或手工连接验证

### Task 3.2: 订单频道按当前用户订阅
- **Location**: `backend/app/api/ws.py`
- **Description**: `/ws/orders` 不再信任 query 中的 `user_id`，直接使用 token 中的 user id。
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - 前端可去掉或忽略 `user_id`
  - 伪造 `user_id` 不会订阅他人频道
- **Validation**:
  - 使用两个不同 token 手工验证 Redis channel

### Task 3.3: 策略信号订阅校验归属
- **Location**: `backend/app/api/ws.py`, `backend/app/services/strategy.py`
- **Description**: `/ws/signals` 根据 `strategy_id` 查 DB，确认策略属于当前用户或当前用户具备管理员权限。
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - 不存在策略返回关闭/错误
  - 非 owner 普通用户无法订阅
- **Validation**:
  - 新增权限测试；手工用 viewer/trader/admin token 验证

## Sprint 4: 流式 AI 请求刷新机制

**Goal**: 让 AI 聊天和图表分析在 access token 过期时可恢复，而不是直接 401。

**Demo/Validation**:
- access token 过期后，打开 AI 页面可自动 refresh 并继续流式输出

### Task 4.1: 抽取 fetch-with-refresh helper
- **Location**: `frontend/src/api/ai.ts`, `frontend/src/api/ai_chart.ts`, 可新建 `frontend/src/api/streamClient.ts`
- **Description**: 为 SSE over fetch 封装一次 401 refresh + retry，逻辑与 axios client 保持一致。
- **Dependencies**: Sprint 1
- **Acceptance Criteria**:
  - 只重试一次，避免死循环
  - 保留 AbortSignal 支持
- **Validation**:
  - `pnpm --dir frontend build`
  - 手工让 access token 过期后测试 AI 页面

### Task 4.2: 统一错误反馈
- **Location**: `frontend/src/api/ai.ts`, `frontend/src/api/ai_chart.ts`, `frontend/src/utils/feedback.ts`
- **Description**: refresh 失败时给出登录失效反馈并跳转 `/login?from=...`。
- **Dependencies**: Task 4.1
- **Acceptance Criteria**:
  - 与 axios 401 行为一致
  - 不吞掉服务端 SSE `[ERROR]` 内容
- **Validation**:
  - 手工断开 refresh cookie 验证跳转

## Sprint 5: 测试稳定性与质量门禁

**Goal**: 让自动检测输出可作为可靠信号。

**Demo/Validation**:
- 后端 `pytest` 全绿
- 前端 `build` 通过
- lint/typecheck 至少达到可持续修复状态

### Task 5.1: 修复系统管理测试隔离
- **Location**: `backend/tests/test_system_api.py`, `backend/tests/conftest.py`
- **Description**: 避免 TestClient 多次请求复用真实 asyncpg 连接池导致 Windows event loop closed。优先方案是测试中覆盖 `get_db` 到测试 async session，或确保每个 TestClient 生命周期内正确 init/dispose engine。
- **Dependencies**: Sprint 1
- **Acceptance Criteria**:
  - `uv --directory backend run pytest tests/test_system_api.py -q` 稳定通过
  - `uv --directory backend run pytest -q` 不再出现 event loop closed
- **Validation**:
  - 连续运行 pytest 两次

### Task 5.2: 补齐 ESLint 9 配置
- **Location**: `frontend/eslint.config.js`
- **Description**: 新增 ESLint flat config，覆盖 React/TypeScript 基础规则，并与当前 Vite/TS 项目兼容。
- **Dependencies**: 无
- **Acceptance Criteria**:
  - `pnpm --dir frontend lint` 不再因缺配置直接失败
  - 初始规则不引入大量无关阻断
- **Validation**:
  - `pnpm --dir frontend lint`

### Task 5.3: 分类处理 ruff 问题
- **Location**: `backend/app/**`, `backend/tests/**`, `backend/scripts/**`
- **Description**: 先自动修复 import/unused/datetime.UTC 等安全项，再人工处理 B008/B904/ASYNC109/F841/B905 等需要判断的项。
- **Dependencies**: Sprint 2
- **Acceptance Criteria**:
  - `uv --directory backend run ruff check .` 通过或只剩明确豁免项
  - 不改变业务行为
- **Validation**:
  - `uv --directory backend run ruff check .`
  - `uv --directory backend run pytest -q`

### Task 5.4: 处理 mypy 高价值错误
- **Location**: `backend/app/core/backtest_engine.py`, `backend/app/api/system.py`, `backend/app/services/ai.py`, `backend/app/db/redis_client.py`, `backend/app/deps.py`
- **Description**: 优先修复可能隐藏运行时风险的 None 访问、Redis close API、OpenAI stream 类型、DataScope Literal 类型。
- **Dependencies**: Task 5.3
- **Acceptance Criteria**:
  - `uv --directory backend run mypy app` 通过，或剩余项有注释说明
- **Validation**:
  - `uv --directory backend run mypy app`

## Sprint 6: 回归与交付

**Goal**: 确认项目可启动、可登录、核心页面可用。

**Demo/Validation**:
- 用户能登录 `http://localhost:5173/`
- 侧栏按权限显示
- 行情、策略、回测、模拟交易、AI 页面无明显前端崩溃

### Task 6.1: 后端回归
- **Location**: `backend/tests`
- **Description**: 跑完整测试和迁移检查。
- **Dependencies**: Sprint 2-5
- **Acceptance Criteria**:
  - `pytest` 全绿
  - `alembic current` 等于 head
- **Validation**:
  - `uv --directory backend run pytest -q`
  - `uv --directory backend run alembic current`

### Task 6.2: 前端回归
- **Location**: `frontend/src`
- **Description**: 跑类型检查、构建、lint，并手工浏览关键页面。
- **Dependencies**: Sprint 4-5
- **Acceptance Criteria**:
  - `pnpm --dir frontend build` 通过
  - `pnpm --dir frontend lint` 通过或只剩明确可接受警告
- **Validation**:
  - `pnpm --dir frontend build`
  - `pnpm --dir frontend lint`

## Testing Strategy

- 后端最小回归：`uv --directory backend run pytest tests/test_health.py tests/test_system_api.py -q`
- 后端全量回归：`uv --directory backend run pytest -q`
- 后端质量门禁：`uv --directory backend run ruff check .` 和 `uv --directory backend run mypy app`
- 前端质量门禁：`pnpm --dir frontend build` 和 `pnpm --dir frontend lint`
- 启动验证：后端 `python run.py`，前端 `pnpm dev`，浏览器访问 `http://localhost:5173/`

## Potential Risks & Gotchas

- WebSocket 鉴权如果直接依赖 HTTP `Depends`，可能不适配 WS 生命周期；应写专用解析函数。
- AI 流式 fetch 如果 retry 时复用已消费的 Request body，会失败；应重新构造请求。
- 系统管理测试如果继续打真实 PG，会受本地数据和事件循环影响；建议专门测试 DB 或 dependency override。
- ruff 自动修复不要一次性混入业务修复提交，避免审查困难。
- Alembic 升级会改本地 DB 状态，执行前应确认当前库是开发库。

## Rollback Plan

- 代码修复逐 sprint 提交；单个 sprint 出问题可回退对应 commit。
- 数据库迁移 `b1c2d3e4f5a6` 只新增/删除权限点，可用 `uv --directory backend run alembic downgrade 7aaf2f5c947e` 回退。
- 前端 ESLint 配置若阻断开发，可先放宽规则或临时只运行 `pnpm --dir frontend build`。
