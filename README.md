# TCAlpha

> 基于 AKShare 的 A 股量化分析、回测与模拟交易 Web 平台 · 含 RBAC 鉴权 + AI 助手 + 实时行情 WS。

**当前版本**: v0.8.34 — 因子值缓存提速（因子快照 Redis 缓存 + 收盘 beat 刷新）

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 19 + TypeScript 5 + Vite 7 + Ant Design 5 + TailwindCSS 4 + Zustand + React Query + ECharts + lightweight-charts |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Alembic |
| 数据库 | PostgreSQL 16（关系数据）+ ArcticDB（K 线 / Tick 时序数据） |
| 缓存 / 队列 | Redis 7 + Celery 5（beat + worker） |
| 数据源 | AKShare（A 股免费数据） |
| 策略框架 | VNPY 4.3（仅复用 BarData / TickData / ArrayManager / CtaTemplate） |
| AI | OpenAI 兼容 API（DeepSeek / Claude / 智谱 GLM） |
| 鉴权 | JWT（access 15min 内存 + refresh 30d HttpOnly cookie）+ RBAC（角色 / 18 权限点 / 数据范围） |
| 部署 | Docker Compose + Nginx + HTTPS |

## 目录

```
tcalpha/
├── backend/      FastAPI 三层（api / services / db） + Celery + 策略 + 核心引擎
├── frontend/     React + Vite + AntD
├── docs/         部署 / 修复计划等文档
├── scripts/      启动 / 工具脚本（PowerShell + Python）
├── .run/         PyCharm Run 配置（提交进库共享）
├── docker-compose.yml
├── start-backend.bat / start-frontend.bat
└── .env.example
```

## 快速开始（开发）

### 首次环境准备

```bash
# 1. 起 PG + Redis
docker compose up -d

# 2. 后端依赖 + .env + 迁移
uv --directory backend sync
cp .env.example .env          # 改 JWT_SECRET / DATABASE_URL / REDIS_URL
uv --directory backend run alembic upgrade head

# 3. 创建超级管理员（交互式）
uv --directory backend run python scripts/create_admin.py

# 4. dev 早期：灌 50 只热门股，前端搜索 / 下拉立即可用
uv --directory backend run python scripts/seed_symbols.py

# 5. 前端依赖
pnpm --dir frontend install
```

### 启动后端 + 前端

最舒服的方式（**推荐**）：**PyCharm 打开仓库根目录** → 顶栏 ▶ 选「Backend (run.py)」+「Frontend (Vite)」。

或资源管理器双击 `start-backend.bat` + `start-frontend.bat`（Windows）。

终端流：

```bash
make back-safe                # uvicorn 热重载（自动选可用端口，写 frontend/.dev-port）
make front                    # Vite :5173
make worker                   # Celery worker（跑回测/数据下载/AI 盯盘时需要）
make beat                     # Celery beat（定时任务）
make notify                   # 通知分发 worker（飞书推送）
```

浏览器 <http://localhost:5173> → 登录 → 进工作台。后端 API 端口由 `frontend/.dev-port` 决定（动态），不是固定 8000。

详见：[`backend/README.md`](backend/README.md) · [`frontend/README.md`](frontend/README.md)

## 路线图

- [x] Phase 0：项目骨架 + Docker + Hello World
- [x] Phase 1：AKShare 数据下载 + ArcticDB + `/api/market`
- [x] Phase 2：前端布局 + K 线图 + WebSocket 实时行情
- [x] Phase 3：策略管理 + 回测（Celery 异步）
- [x] Phase 4：实时策略 worker + 模拟撮合
- [x] Phase 5：AI 助手（DeepSeek SSE） + 飞书通知 + AI 盯盘 + 图表 AI 分析
- [x] Phase 6：鉴权基础（Basic Auth → v0.7.0 切 JWT）
- [x] **Phase 7：RBAC 完整链路**
  - v0.7.0 后端基础（DB + JWT + auth 路由）
  - v0.7.1 业务路由挂权限闸门
  - v0.7.2 用户 / 角色管理 UI
  - v0.7.3 启动稳定性 + 登录跳转修复
  - v0.7.4 代码审查批量修复（安全 / 正确性 / 性能 / 健壮性）
  - v0.7.5 时区统一（Asia/Shanghai）
  - v0.7.6 前端按钮权限收紧 + 热门股 seed
- [x] **v0.8.0：量化能力扩充**（功能迭代，跨 Phase）
  - 策略库扩到 5 类（MA / RSI / MACD / 布林带 / 海龟唐奇安）+ 参数表单动态化
  - 回测引擎：网格扫参（热力图）+ 多策略对比 + A 股涨跌停撮合约束 + AI 归因
  - 选股器：多因子打分（动量 / 估值 / 换手）+ 选股闭环（加自选 / 去回测 / 建策略）
  - 盯盘驾驶舱：自选实时报价 + AI 告警聚合
  - 统一数据层 DataProvider + 数据同步水位表 + GitHub Actions CI
- [x] **Phase 8：数据权限落地** —— `effective_scope` 全链路（backtest / sweep / sim / strategy / ai_alerts）；`dept` 无部门模型退化为 `self`；自选 / 通知规则刻意 self-only（个人配置 + webhook 密钥安全）
- [ ] Phase 9（进行中）：实盘 Gateway 接入 + 多账户 —— v0.8.6 已落地 BaseGateway 契约 + 工厂 + 配置切换 + 模拟资金账户；实盘网关（QMT/xtquant）待环境就绪后接入

## 鉴权速览（v0.7.x）

- 登录：`POST /api/auth/login { username, password }` → 返回 access token + 写 refresh cookie
- 业务接口：`Authorization: Bearer <access>`
- 角色：**admin**（super，18/18） / **trader**（14/18） / **viewer**（6/18 只读）
- 权限点 18 个，分类：`system` / `strategy` / `sim` / `backtest` / `data` / `ai` / `notify`

UI 上 viewer 看到的写按钮会 disabled 并带 Tooltip 提示缺什么权限，删除按钮直接隐藏。后端路由 `require_permission(...)` 是真正的安全边界。

## 文档

- [`CHANGELOG.md`](CHANGELOG.md) — 完整版本日志
- [`backend/README.md`](backend/README.md) — 后端开发 + 鉴权细节 + 常见坑
- [`frontend/README.md`](frontend/README.md) — 前端开发约定 + PermButton 用法
- [`docs/deploy.md`](docs/deploy.md) — 生产部署

## License

MIT
