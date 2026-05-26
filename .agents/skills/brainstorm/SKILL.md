---
name: brainstorm
description: 当需要探索方案、头脑风暴、创意思维、对比设计选择时使用。触发词：头脑风暴、方案、怎么设计、有什么办法、创意、讨论、探索、建议、怎么做、如何实现
---

# 头脑风暴

## TCAlpha 技术边界（所有方案必须落在此栈内）

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Alembic |
| 任务 | Celery 5 + Redis broker |
| 数据库 | PostgreSQL 16（关系）+ ArcticDB（时序 K 线 / Tick） |
| 缓存 / 消息 | Redis 7（缓存 + Celery + pub/sub WS） |
| 数据源 | AKShare（A 股，免费，有限流，分钟级） |
| 策略框架 | VNPY 4.3（仅复用 BarData / ArrayManager / CtaTemplate） |
| 前端 | React 19 + Vite 7 + AntD 5 + Tailwind 4 + Zustand + React Query |
| 图表 | ECharts（指标、统计） + lightweight-charts（高性能 K 线） |
| AI | OpenAI 兼容 API |
| 部署 | Docker Compose + Nginx + HTTPS |

## 思维框架

### 发散
1. 不评判：先把所有想法列出来
2. 跨界借鉴：聚宽 / 米筐 / vnTrader / TradingView 怎么做？
3. 反向思考：如果**不做**这个功能会怎样？
4. Python 生态：有没有现成 lib 解决？

### 收敛
1. **复用优先**：能搬观澜代码吗？能用现成 lib 吗？
2. **三层定位**：路由 / service / db 哪一层？前端 page / store / api？
3. **同步 or 异步任务**：阻塞 < 1s 走 endpoint；耗时走 Celery
4. **持久 vs 缓存**：PG（持久）/ ArcticDB（时序）/ Redis（缓存与广播）
5. **限流安全**：AKShare 限流 → Celery 串行 + Redis 锁
6. **公网部署**：是否泄漏密钥？是否走 Nginx？是否需 HTTPS？

## 评估矩阵

| 维度 | 1 分 | 5 分 |
|---|---|---|
| 复用度 | 全新写 | 完全搬观澜/lib |
| 可行性 | 风险高 | 完全可行 |
| 开发量 | > 5 天 | < 0.5 天 |
| 性能 | 同步阻塞 | 异步 + 缓存 |
| 安全 | 有漏洞 | 公网安全 |
| UX 一致 | 自定义控件 | 纯 AntD |

## 数据存储决策树

```
持久化？
├ 是 → 数据形态？
│  ├ 关系/状态/订单/策略元数据  → PostgreSQL
│  ├ 时序（K 线 / Tick / 因子）  → ArcticDB
│  └ 大文件                     → 文件系统 + PG 存路径
└ 否 → 作用域？
   ├ 跨进程/跨用户广播  → Redis pub/sub
   ├ 单进程短期         → Python 进程内字典
   └ 前端会话状态       → Zustand
```

## 业务逻辑放置决策树

```
是否纯参数校验？   → 路由层（api/）
是否要发出请求/查 DB → service 层（services/）
是否要落库       → ORM 或 db 子层
是否耗时 > 2 秒  → Celery 任务（tasks/）
是否要实时推送   → Redis pub/sub + WS endpoint
```

## 常见陷阱

| ❌ 错的 | ✅ 对的 |
|---|---|
| 路由里直接调 AKShare | service 包一层 + Celery 限流 |
| 前端 fetch 第三方 API | 后端代理 + 缓存 + 跨域控制 |
| 用 PG 存 K 线 | 用 ArcticDB（PG 存元数据） |
| Celery 单 worker 跑实时策略 | 长跑 task + 心跳 + 重启策略 |
| WebSocket 单进程广播 | Redis pub/sub 多 worker 广播 |
| 用 SQLAlchemy 同步 API | 用 async API + AsyncSession |
| 把密钥写 docker-compose.yml | 走 .env + Secrets |

## 输出模板

```markdown
## 问题
- 是什么 / 为什么重要 / 当前状态

## 方案 A: <name>
- 描述
- 落点: api/services/db/tasks/前端page
- 数据库变更
- 优点 / 缺点
- 评分（复用度 / 可行性 / 开发量 / 性能 / 安全 / UX）= ?/30

## 方案 B: <name>
（同上）

## 推荐 + 理由
## 实施步骤（1..N）
```
