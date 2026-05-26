# TCAlpha Backend

FastAPI + Celery + SQLAlchemy + ArcticDB

## 开发命令

```bash
uv sync                                       # 装依赖
cp ../.env.example ../.env                    # 配置
uv run alembic revision --autogenerate -m "init"   # 首次迁移
uv run alembic upgrade head
```
```bash
uv run uvicorn app.main:app --reload          # http://localhost:8000
```

## 目录约定

```
app/
├── main.py             FastAPI 入口
├── config.py           Pydantic Settings 配置
├── deps.py             FastAPI Dependency 工厂
├── api/                路由（仅参数校验 + 调 service）
├── services/           业务逻辑
├── db/                 PG / Redis / ArcticDB 连接 + ORM
├── schemas/            Pydantic 出入参 DTO
├── tasks/              Celery 任务
├── core/               核心抽象（gateway / backtest engine / pubsub）
├── strategies/         策略代码（用户可编辑）
├── indicators/         指标插件
└── utils/              工具函数
```

## 规范

- 所有路由通过 `Depends(get_db)` 获取 session，禁止全局 session
- 所有配置走 `from app.config import settings`，禁止 `os.environ.get`
- 路由层只做参数校验和 service 调用，业务逻辑在 service
- 数据库操作走 SQLAlchemy 2.0 异步 API
