---
name: tech-decision
description: 技术选型评估 / 库对比 / 架构决策记录。触发词：技术选型、选择方案、库对比、技术评估、ADR、架构决策
---

# 技术决策

## 已锁定的决策（不轻易动）

| 决策点 | 选择 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 异步、Pydantic 原生、OpenAPI 自带 |
| ORM | SQLAlchemy 2.0 async | 生态最广、支持 async + 同步 |
| 迁移 | Alembic | SQLAlchemy 官方配套 |
| 任务队列 | Celery + Redis | 最成熟，beat 内置 |
| 时序库 | ArcticDB | 嵌入式无运维，K 线性能 |
| 关系库 | PostgreSQL | 生产首选 |
| 数据源 | AKShare | 免费够用（前期） |
| 策略框架 | VNPY（部分） | 复用 BarData/ArrayManager，去掉 EventEngine |
| 前端框架 | React 19 | 生态、AntD 配套 |
| UI 库 | Ant Design 5 | 表单 / 表格 / 弹窗最全 |
| 状态 | Zustand + React Query | 服务器/客户端状态分离 |
| 图表 | ECharts + lightweight-charts | 通用 + K 线高性能 |
| 包管理 | uv（py） + pnpm（ts） | 最快 + 省空间 |
| 部署 | Docker Compose + Nginx | 个人版友好 |

## 技术选型对比表（已评估）

### Web 框架

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **FastAPI** | 异步原生、Pydantic 集成、OpenAPI 自带 | 相对 Django 生态较小 | ✅ 已采纳 |
| Django REST | 生态最大、Admin 完善 | 同步优先、ORM 异步支持弱 | ⭕ |
| Litestar | 性能更高 | 社区小、文档少 | ⭕ |

### ORM

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **SQLAlchemy 2.0 async** | 生态最广、async 完整 | 学习曲线陡 | ✅ 已采纳 |
| Tortoise ORM | 轻量、async 原生 | 生态小、迁移弱 | ⭕ |
| Peewee | 简单易用 | 无 async | ⭕ |

### 时序数据存储

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **ArcticDB** | 嵌入式无运维、K 线读写极快 | 不支持网络访问、单机 | ✅ 已采纳 |
| InfluxDB | 标准时序数据库、可网络访问 | 需单独部署、Query 语法复杂 | ⭕ |
| TimescaleDB | PG 扩展、SQL 兼容 | 需额外安装、大数据性能不如专用 | ⭕ |
| Parquet + S3 | 成本低、可分析 | 无实时能力、读写延迟高 | ⭕ |

### 任务队列

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **Celery + Redis** | 最成熟、beat 内置、生态完善 | 进程重 | ✅ 已采纳 |
| RQ (Redis Queue) | 轻量、简单 | 无 beat、功能有限 | ⭕ |
| APScheduler | 纯 Python、无 broker | 不支持分布式 | ⭕ |
| Dramatiq | 性能好 | 社区小 | ⭕ |

### 前端状态管理

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **Zustand（UI）+ React Query（服务器）** | 服务器/客户端状态分离、轻量 | 需要两套思维 | ✅ 已采纳 |
| Redux Toolkit | 功能强大、DevTools 强 | 样板代码多 | ⭕ |
| Jotai | 原子化、灵活 | 调试相对复杂 | ⭕ |
| SWR | 轻量、Next.js 原生 | mutation 不如 React Query | ⭕ |

### K 线图表

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **lightweight-charts** | 金融级性能、100万 bar 流畅 | 功能相对单一 | ✅ 已采纳（K 线） |
| **ECharts** | 功能全面、中文文档好 | 大数据量性能一般 | ✅ 已采纳（指标/统计） |
| TradingView Charting Library | 专业金融图表 | 商业授权 | ⭕ |
| Highcharts | 功能完善 | 商业授权 | ⭕ |

### 实时推送

| 方案 | 优点 | 缺点 | 本项目 |
|------|------|------|--------|
| **WebSocket + Redis pub/sub** | 多 worker 广播、低延迟 | 连接管理复杂 | ✅ 已采纳 |
| SSE | 简单、HTTP/1.1 兼容 | 单向、不适合双向控制 | ✅（AI 流式输出） |
| Long Polling | 兼容性最好 | 延迟高、服务器压力大 | ⭕ |

---

## 决策模板（ADR 简版）

```markdown
# ADR-NNN: <决策标题>

- 日期：YYYY-MM-DD
- 状态：proposed / accepted / superseded by ADR-XXX

## Context
- 当前状况、约束、问题

## Options
| 方案 | 优点 | 缺点 |
|---|---|---|
| A | ... | ... |
| B | ... | ... |

## Decision
选 <方案>，理由：...

## Consequences
- 正面：...
- 负面 / 妥协：...
- 影响范围：哪些模块要改
```

## 何时立 ADR

- 引入新一级依赖（如换 Celery 为 RQ）
- 改架构层次（如加 GraphQL 层）
- 数据模型大改（如分库分表）
- 安全/合规相关（如鉴权方案换 JWT → OAuth）

不需要立 ADR 的：bug 修复、小重构、UI 调整、依赖小版本更新

## 决策反模式

- ❌ "因为别人用所以我也用"
- ❌ "未来可能用到，先引进来"（YAGNI）
- ❌ "这个 lib 看起来很 cool"
- ❌ 选型只看 GitHub Star

## 常见决策点参考

| 问题 | TCAlpha 建议 |
|---|---|
| 行情实时推送怎么做？ | FastAPI WS + Redis pub/sub，多 worker 广播 |
| 回测要不要并行？ | Celery 多 worker，单次回测内串行（vnpy 限制） |
| 是否引入 GraphQL？ | 不引入，FastAPI + Pydantic OpenAPI 够用 |
| 前端用 SWR 还是 React Query？ | React Query（mutation 更强、cache 更灵活） |
| 用 ORM 还是 raw SQL？ | ORM 优先，性能极致才下降到 raw |
| ArcticDB vs InfluxDB？ | ArcticDB（嵌入式无运维，K 线读写更快） |
| 是否引入消息队列（Kafka/RabbitMQ）？ | 暂不，Redis Streams 够 |
