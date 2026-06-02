# TCAlpha 部署指南（v0.7.x）

> 目标读者：把 TCAlpha 部署到一台 Linux VPS 或本机 docker 模拟上线。当前版本 **v0.7.6**，鉴权走 JWT + RBAC。

## 0. 路线图

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.6.0 | Basic Auth + 严格 CORS + `.env.prod` 模板 | ✅ 已被 v0.7 JWT 取代 |
| v0.7.0 | JWT（access + refresh）+ RBAC 后端 | ✅ |
| v0.7.1 | 业务路由挂权限闸门 | ✅ |
| v0.7.2 | 用户/角色管理 UI | ✅ |
| v0.7.3–v0.7.5 | DX / 时区 / 测试 / 代码审查修复 | ✅ |
| v0.7.6 | 前端按钮权限收紧 + 热门股 seed | ✅ |
| v0.8.x | 数据权限 `data_scope` 落地 | 计划 |
| v0.9.x | Docker 化 + Nginx/Caddy 反代 + HTTPS + 自动备份 | 计划 |

## 1. 上线前置清单

- [ ] 一台机器（VPS 或本机 docker desktop）
- [ ] 安装 Python 3.13 + Node 20 + pnpm + uv（或后续 v0.9 切 Docker 镜像）
- [ ] 安装并启动 PostgreSQL 16 + Redis 7（或 `docker compose up -d` 用本仓库的 compose）
- [ ] 克隆仓库 + `uv --directory backend sync` + `pnpm --dir frontend install`
- [ ] 用 `.env.example` 复制 `.env`，**关键 4 项**：
  - `JWT_SECRET`：随机 32+ 字节字符串（**生产必须改**）
  - `DATABASE_URL` / `DATABASE_URL_SYNC`：PG 连接串
  - `REDIS_URL`：Redis 连接串（broker / cache / pub-sub 共用 db 0/1/2）
  - `CORS_ORIGINS`：前端域名（公网部署不含 `localhost`）
- [ ] 应用 alembic 迁移：`uv --directory backend run alembic upgrade head`
- [ ] 创建超级管理员：`uv --directory backend run python scripts/create_admin.py`
- [ ] 启动后端 + worker + beat + notify + 前端
- [ ] 浏览器访问 → 自动跳 `/login` → 输入账密 → 进入工作台

## 2. 安全自检（v0.7.6）

### 必须做

- [x] `JWT_SECRET` 改成随机 32+ 字节（**绝不**使用 `.env.example` 默认值）
- [x] `CORS_ORIGINS` 不含 `localhost`（公网部署）
- [x] `.env` **绝不**入仓（`.gitignore` 已配）
- [x] `.env` 文件权限 600（Linux）
- [x] `DEBUG=false` 时不暴露 traceback 到前端
- [x] admin 密码 ≥ 8 位（用 `scripts/create_admin.py` 创建）
- [x] **refresh cookie**：HttpOnly + SameSite=Strict + `Path=/api/auth`；生产开 `Secure`（HTTPS）

### v0.7.6 已有的安全特性

- ✅ JWT access token 15 min，refresh 30 d
- ✅ Logout 拉黑 access + refresh 的 jti（Redis 黑名单到 token 自然过期）
- ✅ refresh 旋转：每次刷新拿到新对，旧 jti 立即拉黑（防重放）
- ✅ 登录失败也跑 bcrypt 校验，抹平响应时延差异（防用户名枚举）
- ✅ 业务路由 `require_permission(...)` 闸门，super 用户绕过
- ✅ 防自残：admin 不能删自己 / 停用自己 / 从 admin 角色摘自己；内置 admin 角色禁删
- ✅ 前端按钮 disabled + Tooltip 提示需要的权限（v0.7.6）

### 仍待 v0.9 解决

- [ ] HTTPS（强烈建议 v0.7.x 阶段也用 Caddy 反代上 HTTPS，refresh cookie 才能开 Secure）
- [ ] 登录端点限流（4 位密码爆破依然可能；建议 Nginx/Caddy `limit_req`）
- [ ] 安全 header（HSTS / CSP / X-Frame-Options 等）→ Caddy / Nginx 层加

## 3. 创建超级管理员

```bash
uv --directory backend run python scripts/create_admin.py
# username (default=admin): admin
# display name (可选): 张三
# password (≥8 位): ********
# confirm  :        ********
# ✓ admin created: id=1 username=admin
```

完成后用户表里的 admin 用户：`is_super=true` + 绑 `admin` 角色（18/18 权限）。

## 4. 启动流程（本机模拟）

### Dev / 本机模拟（PyCharm 或终端）

```bash
# 1. 启动依赖
docker compose up -d

# 2. 应用迁移
make migrate

# 3. dev 早期可选：灌热门股，前端立即能搜
uv --directory backend run python scripts/seed_symbols.py

# 4. 5 个进程（5 个终端 / tmux / supervisord）
make back-safe   # FastAPI 动态端口（写 frontend/.dev-port）
make worker      # Celery worker
make beat        # Celery beat
make notify      # 通知分发 worker
make front       # Vite :5173

# 5. 浏览器 http://localhost:5173 → /login → 输 admin 账号 → 进入
```

### 生产（暂无 Docker 化，先用进程管理器）

```bash
# systemd / supervisord 跑 5 个进程
# uvicorn 改用固定端口 + 不要 --reload：
uv --directory backend run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4

# Caddy / Nginx 反代 :8000 → 443，把 /api 和 /ws 都转发；前端打包 dist/ 走静态资源
pnpm --dir frontend build
# 把 frontend/dist/ 部署到 Caddy / Nginx root
```

## 5. 验证清单

### 后端 API 鉴权

```bash
# 1. 不带 token：业务接口应 401
curl -i http://127.0.0.1:8000/api/notify/event-types
# HTTP/1.1 401 Unauthorized

# 2. 登录拿 access token
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"<pwd>"}'
# {"access_token":"eyJ...", "expires_in":900, "user_id":1}

# 3. 带 token 调业务接口
TOK="eyJ..."
curl -i -H "Authorization: Bearer $TOK" http://127.0.0.1:8000/api/notify/event-types
# HTTP/1.1 200 OK

# 4. /health 永远公开（用于 LB 探活）
curl -i http://127.0.0.1:8000/health
```

### RBAC 验证

```bash
# 用 admin 拿到 token 后调 /me，看权限列表
curl -s -H "Authorization: Bearer $TOK" http://127.0.0.1:8000/api/auth/me
# {"id":1,"username":"admin","is_super":true,"roles":["admin"],"permissions":[...18 条...],"data_scope":"all",...}
```

### WebSocket 鉴权

浏览器 WS 不能发 header，前端 `wsUrl()` 会把 access token 拼到 `?token=`。后端 `api/ws.py` 解析 query 校验 JWT。

### CORS

把 `CORS_ORIGINS` 改成 `https://example.com` 后从 `http://localhost:5173` 调用 `/api/*`：浏览器应拦截（CORS error）。

## 6. 常见问题

| 症状 | 原因 | 修复 |
|------|------|------|
| 启动后所有请求 401 | 没带 Bearer token / token 过期 | 前端 v0.7.0b 已自动 refresh；后端用 curl 时手动登录拿新 token |
| 业务端点 403 `missing permission: xxx` | 当前角色没有这条权限 | 用 admin 在「角色管理」勾上对应权限；或换 super 用户 |
| 登录 200 但 `/me` 401 | access token 过期（15 min）/ jti 黑名单 | 前端自动 refresh；dev 时手动重启清 Redis db 0 |
| 浏览器 F5 后立刻被弹回 /login | `bootstrap()` 走 refresh 失败（cookie 没了 / 后端重启清了黑名单） | v0.7.3 已修；继续看 Network 里 `/api/auth/refresh` 响应 |
| alembic head 多个 | 多人改了迁移 | `alembic merge -m "merge" head1 head2` |
| AsyncSession `greenlet_spawn` 报错 | lazy load 在 async 里没用 selectinload | service 里改 `.options(selectinload(X.children))` |
| Celery 任务不执行 | worker 没跑 / 模块没 include | `tasks/celery_app.py` include 列表 + `make worker` |
| `BackTestJob ... not bound to Session` | 跨 session 访问 ORM 属性 | v0.7.4 已修；自己写 task 时 session 内提取字段为局部变量 |

## 7. 下一步（v0.8 / v0.9）

完成 v0.7.6 后：

- **v0.8.x 数据权限**：`data_scope=self/dept/all` 真正落地到 service 层查询
- **v0.9.0 Docker 化**：5 进程容器化，`docker compose up -d` 一键启动
- **v0.9.1 反代 + HTTPS**：Caddy/Nginx 反代 + 自动证书 + 域名
- **v0.9.2 可观测性**：日志滚动 + Prometheus 指标 + 健康检查强化
- **v0.9.3 容灾**：PG 备份 + ArcticDB 备份 + 一键回滚
