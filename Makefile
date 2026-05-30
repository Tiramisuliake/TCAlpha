# TCAlpha 开发命令集
.PHONY: help up down logs back back-safe front worker beat notify migrate revision test fmt lint clean

help:
	@echo "TCAlpha dev commands:"
	@echo "  make up         起 PG + Redis (docker)"
	@echo "  make down       停 PG + Redis"
	@echo "  make logs       看依赖服务日志"
	@echo "  make back       起 FastAPI (开发热重载，端口 8001)"
	@echo "  make back-safe  起 FastAPI 前先清残留进程并起 8001 (Windows)"
	@echo "  make worker     起 Celery worker"
	@echo "  make beat       起 Celery beat"
	@echo "  make notify     起通知分发 worker"
	@echo "  make front      起前端 Vite"
	@echo "  make migrate    运行 alembic upgrade head"
	@echo "  make revision m=\"msg\"  生成新 alembic 迁移"
	@echo "  make test       后端 pytest"
	@echo "  make fmt        ruff format"
	@echo "  make lint       ruff check + mypy"
	@echo "  make clean      清理缓存"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

back:
	cd backend && uv run python run.py

# 同 back（保留别名，兼容旧文档）
back-safe:
	cd backend && uv run python run.py

worker:
	cd backend && uv run celery -A app.tasks.celery_app worker -l info

beat:
	cd backend && uv run celery -A app.tasks.celery_app beat -l info

notify:
	cd backend && uv run python -m app.workers.notify_dispatcher

front:
	cd frontend && pnpm dev

migrate:
	cd backend && uv run alembic upgrade head

revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

test:
	cd backend && uv run pytest

fmt:
	cd backend && uv run ruff format .

lint:
	cd backend && uv run ruff check . && uv run mypy app

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
