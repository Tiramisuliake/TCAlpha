# TCAlpha 部署指南（v0.6.x）

> 目标读者：把 TCAlpha 部署到一台 Linux VPS 或本机 docker desktop 模拟上线的人。

## 0. 路线图回顾

| 版本 | 内容 | 状态 |
|------|------|------|
| **v0.6.0** | Basic Auth + 严格 CORS + `.env.prod` 模板 | 本文档对应 |
| v0.6.1 | 后端 Docker 化（uvicorn / worker / beat / notify 各一容器） | 计划中 |
| v0.6.2 | Caddy 反代 + HTTPS + 域名 | 计划中 |
| v0.6.3 | 日志滚动 + 健康检查强化 | 计划中 |
| v0.6.4 | 自动备份 + 一键回滚 | 计划中 |

## 1. v0.6.0 上线前置清单

- [ ] 准备一台机器（VPS 或本机 docker desktop）
- [ ] 安装 Python 3.13 + Node 20 + pnpm（或后续 v0.6.1 改用 Docker 镜像，无需本机依赖）
- [ ] 安装并启动 PostgreSQL 16 + Redis 7
- [ ] 克隆仓库 + `uv sync` + `pnpm --dir frontend install`
- [ ] 生成 Basic Auth 密码哈希（见 §3）
- [ ] 用 `.env.prod.example` 模板创建 `.env`
- [ ] 应用 alembic 迁移：`make migrate`
- [ ] 启动后端 + worker + beat + notify + 前端
- [ ] 浏览器访问 → 自动跳 `/login` → 输入账密 → 进入工作台

## 2. 安全自检（v0.6.0）

### 必须做

- [x] `AUTH_ENABLED=true`，密码 ≥ 8 位 bcrypt
- [x] `CORS_ORIGINS` 不含 `localhost`（公网部署）
- [x] `.env` **绝不**入仓（`.gitignore` 已配）
- [x] `.env` 文件权限 600
- [x] `DEBUG=false` 时不暴露 traceback 到前端
- [x] `/docs` `/redoc` 受 `AUTH_PROTECT_DOCS=true` 保护

### v0.6.0 仍不够（v0.6.2 解决）

- [ ] HTTPS：当前 HTTP 明文，密码会被中间人嗅探
- [ ] 防爆破：当前没限流，4 位密码 ~10 分钟枚举完
- [ ] Cookie / Session：纯 Basic Auth，每次请求带凭证

> **强烈建议**：v0.6.0 仅在内网或 docker desktop 模拟使用；公网部署必须先做到 v0.6.2。

## 3. 生成密码哈希

```bash
cd backend
uv run python scripts/gen_password_hash.py
# password: ******
# confirm : ******
# 输出：
# AUTH_PASSWORD_HASH=$2b$12$WqumBVV3TO2wx/...
```

把整行复制到 `.env`。

## 4. 启动流程（本机模拟）

```bash
# 1. 启动依赖（如已有 native PG/Redis 跳过）
docker compose up -d

# 2. 应用迁移
make migrate

# 3. 启动 5 个进程（5 个终端 / tmux / supervisord）
make back      # FastAPI :8000
make worker    # Celery worker
make beat      # Celery beat
make notify    # 通知分发 worker
make front     # Vite :5173

# 4. 浏览器打开 http://localhost:5173 → 跳到 /login
```

## 5. 验证清单

### 后端 API 鉴权

```bash
# 不带凭证：应返回 401
curl -i http://localhost:8000/api/notify/event-types

# 带凭证：应返回 200
curl -i -u admin:hello123 http://localhost:8000/api/notify/event-types

# health 永远公开（用于 LB 探活）
curl -i http://localhost:8000/health
```

### WebSocket 鉴权

浏览器 WS 不能发 header，前端 `wsUrl()` 会自动把 base64 凭证拼到 `?token=`。后端 middleware 同时接受 `Authorization` header 与 `?token=`。

### CORS

把 `CORS_ORIGINS` 改成 `https://example.com` 后从 `http://localhost:5173` 调用 `/api/notify/event-types`：浏览器应拦截（cors error）。

## 6. 常见问题

| 症状 | 原因 | 修复 |
|------|------|------|
| 启动后所有请求 401 | `AUTH_PASSWORD_HASH` 为空 | 用 `scripts/gen_password_hash.py` 生成 |
| `/docs` 也要密码 | `AUTH_PROTECT_DOCS=true` | 改 false 或在 `auth_public_paths` 加入 |
| 登录后刷新页面还是跳登录 | sessionStorage 已清 | 浏览器关 tab 后凭证自然失效（设计如此） |
| WS 连不上 | 凭证没拼到 URL | 检查 `wsUrl()` 调用是否替换了硬编码 `ws://localhost:8000/...` |
| AI 盯盘 Celery worker 401 | worker 直接调内部函数不走 HTTP | 不需要带凭证；worker 调 ai.deepseek.com 用 `AI_API_KEY` |

## 7. 下一步

完成 v0.6.0 后：
- v0.6.1 把上述 5 个进程容器化，`docker compose up -d` 一键起
- v0.6.2 加 Caddy 反代 + 域名 + HTTPS
- v0.6.3 + v0.6.4 完成可观测性和容灾
