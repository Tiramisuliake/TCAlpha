# Changelog

## [Unreleased]

## [0.1.0] — 2026-05-26

### Added
- Phase 0：项目骨架（FastAPI + Celery + SQLAlchemy + ArcticDB + React + Docker）
- Phase 1：数据层
  - `Symbol` ORM 模型（symbols 表）
  - AKShare 日 K 下载（限流令牌 + tenacity 重试 + ArcticDB 增量落库）
  - Celery 任务：`refresh_symbol_list` / `download_one_symbol` / `download_daily_kline_all`
  - market API：`GET /api/market/symbols` / `GET /api/market/kline/{symbol}` / `POST /api/market/kline/{symbol}/download`
  - CLAUDE.md 项目规范文档
