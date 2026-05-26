---
name: react-development
description: React 19 / Hooks / 函数组件 / 路由 / 页面组织。触发词：React、组件、page、Hook、useState、useEffect、useMemo、路由、Router
---

# React 开发

## 项目用 React 19 + React Router v7

新页面文件 = `src/pages/<X>/index.tsx`（组件名 PascalCase，文件夹 PascalCase）。

## 页面模板

```tsx
import { useState } from "react";
import { Button, Card, message } from "antd";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getKline } from "@/api/market";

export default function ChartPage() {
  const [symbol, setSymbol] = useState("sh600000");

  const { data, isLoading } = useQuery({
    queryKey: ["kline", symbol],
    queryFn: () => getKline(symbol),
  });

  return (
    <Card title="K 线分析">
      {isLoading ? "加载中…" : <pre className="text-xs">{JSON.stringify(data, null, 2)}</pre>}
    </Card>
  );
}
```

## 添加路由

`src/App.tsx`：

```tsx
<Route path="/chart" element={<Chart />} />
```

侧栏菜单项也加 `<Link to="/chart">` 入口。

## Hooks 规则

1. 只在组件顶层调用，不能在 if / 循环里
2. 自定义 hook 必须 `use` 开头
3. `useEffect` 依赖数组完整列出，让 ESLint react-hooks 帮你
4. 异步操作不放 `useEffect`，放 React Query / useMutation

## useEffect 典型场景

```tsx
useEffect(() => {
  const ws = new WebSocket("...");
  ws.onmessage = (e) => setQuote(JSON.parse(e.data));
  return () => ws.close();          // 一定清理
}, [symbol]);
```

## 列表渲染

```tsx
{items.map((it) => (
  <Card key={it.id}>{it.name}</Card>     // ✅ 唯一 key
))}
```

不要用 index 当 key（除非列表不可重排）。

## 性能要点

- 重组件用 `React.memo` 包
- 派生数据用 `useMemo`
- 事件回调传子组件用 `useCallback`
- 但不要预优化，先实现，性能问题用 React DevTools Profiler 定位

## TypeScript

```tsx
interface KlineProps {
  symbol: string;
  period?: "1m" | "5m" | "1d";
  onSelect?: (bar: Bar) => void;
}

export function Kline({ symbol, period = "1d", onSelect }: KlineProps) {
  // ...
}
```

- props 用 `interface`（可扩展）
- 联合类型用 `type`
- 禁用 `any`，不得已用 `unknown`

## 状态分类

| 类型 | 工具 |
|---|---|
| 服务器数据（list/detail） | React Query `useQuery` |
| 服务器变更 | React Query `useMutation` |
| 跨页面 UI（用户偏好、选中股票） | Zustand store |
| 单组件内 | `useState` |
| URL 同步状态 | `useSearchParams` |
| 不触发渲染的引用 | `useRef` |

## 路径导入

```tsx
import { Bar } from "@/types";          // ✅
import { getKline } from "@/api/market"; // ✅
import { useAuth } from "@/store/auth";  // ✅

import { Bar } from "../../../types";    // ❌
```

## 禁止

- ❌ class 组件
- ❌ Redux（用 Zustand）
- ❌ 内联 style（除非动态计算）；用 Tailwind class
- ❌ `dangerouslySetInnerHTML`（除非来源完全可信）
- ❌ 在组件里直接 axios（走 src/api/*.ts）
