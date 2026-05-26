#!/usr/bin/env node
/**
 * UserPromptSubmit Hook — TCAlpha 强制技能评估
 *
 * 在每条用户消息后追加一个 system-reminder，要求 Claude 先评估
 * 当前问题匹配的技能，然后逐个 Skill() 激活，再开始实现。
 *
 * 跳过条件：上下文恢复 / 斜杠命令。
 */

const fs = require('fs');

let inputData = '';
try { inputData = fs.readFileSync(0, 'utf8'); } catch { process.exit(0); }

let input;
try { input = JSON.parse(inputData); } catch { process.exit(0); }

const prompt = (input.prompt || '').trim();

const skipPatterns = [
  'continued from a previous conversation',
  'ran out of context',
  'No code restore',
  'Conversation compacted',
  'commands restored',
  'context window',
  'session is being continued',
];
if (skipPatterns.some((p) => prompt.toLowerCase().includes(p.toLowerCase()))) process.exit(0);

// 斜杠命令直接放过
if (/^\/[^\/\s]+/.test(prompt.split(/\s/)[0])) process.exit(0);

const instructions = `## 强制技能激活流程（必须执行）

### 步骤 1 — 评估（必须在响应中明确展示）
针对用户问题，列出匹配的技能：\`技能名: 理由\`，无匹配则写"无匹配技能"

可用技能：

**L1 通用：**
- brainstorm: 头脑风暴 / 方案设计 / 功能设计 / 思路探索
- task-tracker: 多步骤任务 / 进度跟踪 / 恢复上下文
- git-workflow: Git / 提交 / 分支 / 双远程（github + gitee） / merge
- code-patterns: 代码规范 / 命名 / Python / TypeScript 编码风格
- tech-decision: 技术选型 / 库对比 / 架构决策
- bug-detective: Bug 排查 / 报错 / 异常 / 调试 / panic
- collaborating-with-codex: Codex 协作
- collaborating-with-gemini: Gemini 协作

**后端 L3（FastAPI + Celery + SQLAlchemy + ArcticDB）：**
- project-navigator: 项目结构 / 文件位置 / 目录速查
- fastapi-development: FastAPI 路由 / Depends / 三层结构 / CORS / 中间件
- sqlalchemy-orm: 模型定义 / async session / 查询 / 关系
- alembic-migration: 迁移 / autogenerate / upgrade / downgrade
- celery-tasks: Celery 任务 / beat 调度 / worker / Redis broker
- arcticdb-ops: ArcticDB / LMDB / 时序数据 / Library / read_batch
- pydantic-models: Pydantic v2 / BaseModel / Field / validate_assignment / DTO
- error-handler: 异常处理 / 全局 handler / loguru / HTTPException
- test-development: pytest / pytest-asyncio / TestClient / httpx mock
- utils-toolkit: 工具函数 / 日期 / 股票代码 / 交易时段 / 限流

**前端 L3（React + Vite + AntD + Tailwind）：**
- react-development: React 19 / Hooks / 组件 / 路由 / 页面
- antd-tailwind-ui: Ant Design 组件 / Tailwind CSS / 布局 / 表单
- zustand-store: Zustand / 全局状态 / persist / slice
- react-query: React Query / useQuery / useMutation / 缓存
- echarts-charts: ECharts / lightweight-charts / K 线 / 指标叠加
- websocket-sse: WebSocket / SSE / 实时行情推送 / 重连

**业务 L4：**
- akshare-fetcher: AKShare / 行情下载 / 限流 / 历史 K 线 / 实时报价
- vnpy-strategy: VNPY BarData / ArrayManager / CtaTemplate / 三层 Params/State/Vars
- backtest-engine: 回测引擎 / 撮合 / 收益曲线 / 最大回撤 / 夏普
- sim-trading: 模拟撮合 / SimGateway / 订单状态机 / 持仓
- ai-services: OpenAI 兼容 / 流式输出 / 多模型切换 / SSE

### 步骤 2 — 激活（逐个 Skill() 调用，等返回再下一个）
- 有 N 个匹配 → 逐次 Skill(...) 调用
- 无匹配 → 写"无匹配技能"，直接进入步骤 3

### 步骤 3 — 实现
所有匹配 Skill() 调用完成后才能开始动手。

---
**关键规则**：
1. ⛔ 不允许评估后跳过 Skill() 直接实现（除非"无匹配技能"）
2. ⛔ 不允许只调用部分技能
3. ⛔ 不允许并行调用 Skill()（必须串行）
4. ✅ 评估 → 串行调用 Skill() → 实现
`;

const out = {
  hookSpecificOutput: {
    hookEventName: 'UserPromptSubmit',
    additionalContext: instructions,
  },
};
console.log(JSON.stringify(out));
