# Changelog

## [Unreleased]

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
