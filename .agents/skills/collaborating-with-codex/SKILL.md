---
name: collaborating-with-codex
description: 与 OpenAI Codex CLI 协同 — 算法/复杂后端逻辑/代码审查/Diff 生成。触发词：Codex、协作、多模型、原型、Diff、算法分析、代码审查
前置：npm install -g @openai/codex；配置 OPENAI_API_KEY
---

# 与 Codex 协同

## 何时让 Codex 介入

- **复杂算法**：回测引擎撮合逻辑、风险指标计算、信号生成
- **代码审查**：让 Codex 看一段我刚写的 Python，挑 bug
- **Diff 生成**：让 Codex 生成 unified diff 应用到本地

## 不让 Codex 做

- 前端样式（用 Gemini 更好）
- 项目结构决策（用 Codex）
- 模糊需求的方案探索（用 Codex 的 brainstorm）

## 标准调用模式

```bash
codex --task "implement a CTA backtest engine for vnpy BarData with commission & slippage, output trades + equity curve" \
      --context backend/app/core/backtest_engine.py
```

或交互式：

```bash
codex
> 给我审查 backend/app/services/market.py 是否有竞态条件
```

## 让 Codex 输出 Diff

```bash
codex --diff --task "add commission field to BacktestJob ORM + alembic migration"
```

得到 unified diff 后人工 review 再 `git apply`。

## 协同流程

1. Codex（我）做规划 + 拆任务
2. 复杂逻辑模块 → Codex 出原型
3. Codex 输出 → Codex review + 集成 + 写测试
4. 写完 → Codex 二次审查

## 注意

- Codex 不知道 TCAlpha 项目上下文，调用时要带 `--context` 文件或在 prompt 里贴关键代码
- Codex 不一定遵守本项目的 code-patterns，输出后 Codex 要按规范调整
- API 用量计费，谨慎重复调用大上下文
