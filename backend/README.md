# TCAlpha Backend

FastAPI + Celery + SQLAlchemy 2.0 + ArcticDB + JWT/RBAC

---

## 一键启动（v0.7.1+）

提供 4 种方式，按你的环境选最顺手的。**所有方式都会先清 8000 端口的残留 uvicorn 进程**，避免 `--reload` 父子僵尸导致的"前端登录网络超时"。

| 方式 | 命令 / 操作 | 适合场景 |
|---|---|---|
| **资源管理器双击** | 双击根目录 `start-backend.bat` | 不想开终端，最直觉 |
| **PyCharm Run** | 顶栏下拉「Backend (uvicorn + 清端口)」→ ▶ | 日常 IDE 开发 |
| **make** | `make back-safe` | Git Bash / WSL / 终端流 |
| **直接跑脚本** | `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/start_backend.ps1` | CI / 别的 IDE |

启动成功标志：终端打印 `Application startup complete.`，浏览器打开 <http://localhost:8000/docs> 能看到 Swagger UI。

---

## 首次环境准备

```powershell
# 1. 装依赖（仓库根）
uv --directory backend sync

# 2. 配 .env（首次必做）
copy .env.example .env
# 然后编辑 .env，至少改 JWT_SECRET / DATABASE_URL / REDIS_URL（如非默认）

# 3. 起 PG + Redis（Docker Compose）
make up

# 4. 跑迁移
make migrate
# 或：uv --directory backend run alembic upgrade head

# 5. 创建超级管理员（交互式，会要 username + password）
uv --directory backend run python scripts/create_admin.py
```

> ⚠️ 本地 dev 默认账号是 `admin / 123456`（v0.7.1 hotfix 调试时设的）。
> **公网部署前务必用 `scripts/create_admin.py` 改强密码**，并且把 `.env` 里 `JWT_SECRET` 换成随机串。

---

## 整套服务起来要哪些进程

| 进程 | 必需性 | 启动 |
|---|---|---|
| PostgreSQL + Redis | 必需（数据 + 缓存 + Celery broker） | `make up` |
| FastAPI (uvicorn) | 必需 | 见上「一键启动」 |
| Vite 前端 | 看你 | 根目录双击 `start-frontend.bat`，或 `make front` |
| Celery worker | 跑回测 / AI 盯盘 / 数据下载时需要 | PyCharm「Celery Worker」配置，或 `make worker` |
| Celery beat | 要定时任务（盯盘 cron）时需要 | PyCharm「Celery Beat」，或 `make beat` |
| 通知分发 worker | 要飞书推送时需要 | `make notify` |

---

## 常用开发命令

```bash
make help              # 全部命令
make back-safe         # 起后端（清端口 + 热重载）
make front             # 起前端
make migrate           # alembic upgrade head
make revision m="msg"  # 生成新迁移
make test              # pytest
make fmt               # ruff format
make lint              # ruff check + mypy
```

直接调（不走 Makefile，不要 `cd backend`）：

```bash
uv --directory backend run uvicorn app.main:app --reload
uv --directory backend run pytest tests/
uv --directory backend run alembic upgrade head
```

---

## 鉴权（v0.7.0+）

- **JWT**：access token 15 min（内存）+ refresh token 30 天（HttpOnly cookie）
- **登录端点**：`POST /api/auth/login` body `{"username":"admin","password":"..."}`
- **当前用户**：`GET /api/auth/me`（Bearer access token）
- **刷新**：`POST /api/auth/refresh`（带 refresh cookie）
- **退出**：`POST /api/auth/logout`（拉黑 access + refresh jti）
- **公开端点**：`/health` `/` `/api/auth/*`（其他全部需 JWT）
- **角色**：admin（super，18/18 权限） / trader（14/18） / viewer（6/18 只读）

业务路由的权限闸门列表见 `app/api/<x>.py` 的 `dependencies=[Depends(require_permission("xxx"))]`。

---

## 目录约定

```
app/
├── main.py             FastAPI 入口 + 路由挂载 + lifespan
├── config.py           Pydantic Settings（读 .env）
├── deps.py             Depends 工厂（get_db / get_current_user_id）
├── api/                路由层（仅参数校验 + 调 service）
│   └── auth.py         登录 / 刷新 / 退出 / me
├── services/           业务逻辑（无 HTTP 知识）
│   └── auth.py         密码校验 + token 签发 / 旋转
├── core/               核心抽象
│   ├── security.py     bcrypt + JWT + Redis 黑名单
│   ├── auth_deps.py    AuthUser + require_permission
│   ├── backtest_engine.py
│   ├── sim_gateway.py
│   └── ...
├── db/                 PG / Redis / ArcticDB 连接 + ORM
│   ├── postgres.py     async engine + Base
│   ├── arctic.py       ArcticDB 单例
│   ├── redis_client.py
│   └── models/         ORM（user / role / permission / strategy / ...）
├── schemas/            Pydantic 出入参 DTO
├── tasks/              Celery 任务
├── strategies/         策略代码
├── indicators/         指标插件
├── middleware/         ASGI 中间件（v0.6 Basic Auth，默认未挂载）
└── utils/              工具函数

scripts/
├── create_admin.py     交互式建/重置超管
├── gen_password_hash.py
└── ...

tests/                  pytest（pytest-asyncio）
alembic/                数据库迁移
```

---

## 常见坑速查

| 症状 | 原因 | 解法 |
|---|---|---|
| 浏览器登录"网络超时" / curl /health 30s 超时 | 8000 端口有多个 LISTENING 僵尸 uvicorn | `make back-safe`（自动清）或手动 `Stop-Process -Id <PID>` |
| 登录 401 但 password 没错 | 进了 `123456` 但 dev DB 改过 | 跑 `scripts/create_admin.py` 重置密码 |
| 登录 200 但 `/api/auth/me` 401 | access token 过期（15 min） / 黑名单 | 前端会自动 refresh；后端 dev 时手动重启清 Redis |
| 业务端点 403 missing permission: xxx | 当前角色没有这条权限 | 切到 admin 或在 DB 给 role 绑 permission |
| alembic head 多个 | 多人改了迁移 | `alembic merge -m "merge" head1 head2` |
| AsyncSession `greenlet_spawn` 报错 | lazy load 在 async 里没用 selectinload | service 里改 `.options(selectinload(X.children))` |
| Celery 任务不执行 | worker 没跑 / 模块没 include | 看 `tasks/celery_app.py` include 列表 + worker 是否启动 |

---

## 规范（强制）

- 所有路由通过 `Depends(get_db)` 获取 session，禁止全局 session
- 所有配置走 `from app.config import settings`，禁止 `os.environ.get`
- 路由层只做参数校验 + 调 service，业务逻辑在 service
- 数据库操作走 SQLAlchemy 2.0 异步 API（`AsyncSession`）
- 路由要权限就用 `Depends(require_permission("xxx"))`，不要手写 `if user.is_super`
- 公开端点请在 `app/main.py` 路由声明时明确写注释「无闸门」
