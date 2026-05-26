# /progress — 项目进度报告

按 Phase 0–6 路线图汇总当前完成度，输出可读报告。

## 步骤

1. 读 `README.md` 的"路线图"区
2. 扫描各 Phase 关键文件是否存在/有内容（不是骨架）：

| Phase | 检查项 |
|---|---|
| 0 | ✅ docker-compose / pyproject / package.json / .env.example 都在 |
| 1 | `app/services/data.py` 非空 + `tasks/data_tasks.py` 有真实实现 + `api/market.py` 接通 ArcticDB |
| 2 | `pages/Chart` 有 K 线组件 + `useWebSocket` 实现 + Redis pub/sub 拉通 |
| 3 | `core/backtest_engine.py` 有 `run()` 实现 + `BacktestJob` ORM CRUD + `pages/Backtest` 完整 |
| 4 | `core/sim_gateway.py` 有 send_order 实现 + `tasks/strategy_tasks.run_strategy` 有循环 + 订单 WS |
| 5 | `services/ai.py` 真实 OpenAI 调用 + `api/ai.py` SSE 通 + 图表 AI 分析 |
| 6 | `docker-compose.prod.yml` + nginx 配置 + HTTPS 文档 |

3. `git log --oneline -20` 看最近活动
4. TaskList 看 in_progress / pending 任务

## 输出

```markdown
# TCAlpha 进度报告 — YYYY-MM-DD

## Phase 路线
- ✅ Phase 0 项目骨架（完成 100%）
- 🚧 Phase 1 数据骨架（完成 ~30%，data_tasks.py 还是 stub）
- ⬜ Phase 2 前端布局
- ⬜ Phase 3 策略 & 回测
- ⬜ Phase 4 实时策略
- ⬜ Phase 5 AI 助手
- ⬜ Phase 6 上线

## 最近 7 天活动
- 5 个 commit，主要在 Phase 0 收尾 + 启动 Phase 1
- 1 个 PR / 任务在进行

## 当前阻塞
- AKShare 在 Windows 下的限流策略未测
- ArcticDB Library 命名约定还没定

## 下一步建议（优先级）
1. 完成 `download_one_symbol` 任务（落 ArcticDB）
2. /api/market/kline 接通真数据
3. 写 5 个端到端测试覆盖 Phase 1
```

输出要诚实——空 stub 不算"已完成"。
