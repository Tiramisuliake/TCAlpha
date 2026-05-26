# /start — 新窗口快速了解 TCAlpha

一次性把项目背景、技术栈、目录、当前阶段、可用命令交给你，新会话不用从头摸索。

## 执行步骤

1. 读 `README.md` 拿到项目目标、技术栈、路线图
2. 读 `CHANGELOG.md`（如果存在）看最近迭代
3. 读 `Makefile` 拿到所有快捷命令
4. `git status` + `git log --oneline -10` 看分支状态和近期提交
5. `ls backend/app/ frontend/src/pages` 看目录
6. 输出"项目快报"：

```markdown
# TCAlpha 项目快报

**形态**：A 股量化分析 + 回测 + 模拟交易 Web 平台

**技术栈**：
- 后端：FastAPI + Celery + SQLAlchemy + ArcticDB + AKShare + VNPY
- 前端：React 19 + Vite + AntD + Tailwind + ECharts + lightweight-charts
- 基建：PostgreSQL + Redis + Docker

**当前阶段**：Phase X（Phase 0 骨架 / Phase 1 数据 / Phase 2 前端 / Phase 3 策略+回测 / Phase 4 实时 / Phase 5 AI / Phase 6 上线）

**最近 3 条 commit**：
- abc1234 ...
- ...

**正在做**（git status / TaskList）：
- ...

**今天可以做的**（基于阶段）：
- ...
```

7. 询问用户："要继续上一个任务，还是开新方向？"
