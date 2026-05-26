# TCAlpha

> 基于 AKShare 的 A 股量化分析、回测与模拟交易 Web 平台。

**状态**: Phase 2 — 前端布局 + K 线图 + 数据管理页

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 19 + TypeScript 5 + Vite 7 + Ant Design 5 + TailwindCSS 4 + Zustand + ECharts + lightweight-charts |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic |
| 数据库 | PostgreSQL 16（关系数据）+ ArcticDB（K 线 / Tick 时序数据） |
| 缓存 / 队列 | Redis 7 + Celery 5（beat + worker） |
| 数据源 | AKShare（A 股免费数据） |
| 策略框架 | VNPY 4.3（仅复用 BarData / TickData / ArrayManager / CtaTemplate 等基础对象） |
| AI | OpenAI 兼容 API（DeepSeek / Claude / 智谱 GLM 等） |
| 部署 | Docker Compose + Nginx + HTTPS（公网部署） |

## 目录

```
tcalpha/
├── backend/      FastAPI 三层（api / services / db） + Celery + 策略 + 指标
├── frontend/     React + Vite + AntD
├── docker-compose.yml
└── .env.example
```

## 快速开始（开发）

```bash
# 1. 起依赖服务
docker compose up -d

# 2. 后端
cd backend
uv sync
cp ../.env.example ../.env  # 然后改里面的值
alembic upgrade head
uvicorn app.main:app --reload  # http://localhost:8000

# 另开终端
celery -A app.tasks.celery_app worker -l info
celery -A app.tasks.celery_app beat -l info

# 3. 前端
cd frontend
pnpm install
pnpm dev  # http://localhost:5173
```

## 路线图

- [x] Phase 0：项目骨架 + Docker + Hello World
- [x] Phase 1：AKShare 数据下载 + ArcticDB + `/api/market`
- [x] Phase 2：前端布局 + K 线图 + WebSocket 实时行情
- [ ] Phase 3：策略管理 + 回测（Celery 异步）
- [ ] Phase 4：实时策略 worker + 模拟撮合
- [ ] Phase 5：AI 助手 + 图表 AI 分析
- [ ] Phase 6：公网部署 + Nginx + HTTPS

## License

MIT
