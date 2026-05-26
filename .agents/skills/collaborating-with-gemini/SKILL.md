---
name: collaborating-with-gemini
description: 与 Google Gemini CLI 协同 — 前端/UI 原型、CSS、React 组件设计、视觉打磨。触发词：Gemini、前端原型、UI 设计、CSS、样式、视觉、组件设计
前置：npm install -g @google/gemini-cli；设置 GEMINI_API_KEY 或 gemini auth login
---

# 与 Gemini 协同

## Gemini 擅长

- React 组件原型（页面布局、表单、表格）
- AntD + Tailwind 组合样式
- ECharts 配置（option 对象巨复杂）
- lightweight-charts 配置
- 设计稿 → 代码（截图描述 → JSX）

## Gemini 不擅长（本项目）

- 后端逻辑（用 Codex 或 Codex）
- VNPY 策略代码（用 Codex）
- 数据库 Schema 设计（用 Codex）

## 调用示例

```bash
# 生成 K 线页面布局
gemini "用 React + AntD + Tailwind 生成 K 线分析页面，左侧股票搜索 + 右侧主图（lightweight-charts）+ 底部副图（MACD）"

# ECharts 复杂 option
gemini --file pages/Backtest/index.tsx "为这个回测结果页加一个收益曲线 + 回撤曲线双轴 ECharts，option 直接给我"
```

## 协同流程

1. Codex 规划页面信息架构和数据流
2. Gemini 出 UI 原型代码
3. Codex review + 改 prop / 类型 / 接 API
4. 联调时遇 CSS / 布局问题 → 再丢 Gemini 改

## 注意

- Gemini 不知道 TCAlpha 的 type 定义、API 形状，调用时贴 `src/types/index.ts` + `src/api/*.ts` 片段
- Gemini 给出的代码可能用旧版本 React API（class 组件、defaultProps），要 review
- 风格上 Gemini 倾向于复杂自定义 CSS，要约束它优先 Tailwind utility class
