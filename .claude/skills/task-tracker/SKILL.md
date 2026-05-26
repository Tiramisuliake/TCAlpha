---
name: task-tracker
description: 多步骤开发任务跟踪 / 进度管理 / 恢复上下文。触发词：任务、待办、TODO、进度、跟踪、继续任务、恢复上下文
---

# 任务跟踪

## 何时启用

- 任务超过 3 步
- 需要跨多文件改动
- 用户说"我想做 X"，X 是 epic 级
- 上下文中断后恢复工作

## 工作流

1. **拆分**：把目标拆成 N 个不超过 1 小时可完成的任务
2. **TaskCreate**：每个任务一条
3. **TaskUpdate(in_progress)**：开始前标记
4. **TaskUpdate(completed)**：完成后立即标记（不要批量）
5. **结束**：TaskList 看是否还有 pending

## 命名规则

| ✅ 好 | ❌ 不好 |
|---|---|
| "写 BacktestEngine.run() 单元测试（5 用例）" | "写测试" |
| "Alembic 加 sim_orders.commission 字段迁移" | "改数据库" |
| "前端 Chart 页面接 /api/market/kline" | "前端" |

## TCAlpha 典型任务模板

### 后端新增 API
- [ ] db/models/<x>.py 加 ORM
- [ ] alembic revision --autogenerate -m "add <x>"
- [ ] schemas/<x>.py 定义 DTO
- [ ] services/<x>.py 写业务逻辑
- [ ] api/<x>.py 写路由（用 Depends）
- [ ] main.py 挂载 router
- [ ] tests/test_<x>.py 写测试

### 前端新增页面
- [ ] pages/<X>/index.tsx
- [ ] types/index.ts 加类型
- [ ] api/<x>.ts 加调用函数
- [ ] App.tsx 加路由
- [ ] App.tsx 侧边栏菜单加入口

### 新增 Celery 任务
- [ ] tasks/<x>_tasks.py 写 @celery_app.task
- [ ] tasks/celery_app.py include 列表加入新模块
- [ ] 若定时 → beat_schedule 加 cron

## 何时清理任务列表

- 一个完整功能交付后归档（不删，标 completed）
- 用户改方向时把废弃任务标 deleted
- 上下文恢复时先 TaskList 看 in_progress 任务
