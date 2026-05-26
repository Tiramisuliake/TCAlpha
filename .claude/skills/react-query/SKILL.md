---
name: react-query
description: TanStack React Query / useQuery / useMutation / 缓存 / refetch / 失效。触发词：React Query、useQuery、useMutation、缓存、refetch、invalidate、staleTime
---

# React Query（TanStack）

`main.tsx` 已注入 QueryClient，默认 `staleTime: 30s, retry: 1`。

## useQuery 模板

```tsx
import { useQuery } from "@tanstack/react-query";
import { getKline } from "@/api/market";

const { data, isLoading, error, refetch } = useQuery({
  queryKey: ["kline", symbol, period],
  queryFn: () => getKline(symbol, period),
  enabled: !!symbol,           // 条件触发
  staleTime: 60_000,           // 1 分钟内不重新请求
});
```

### queryKey 规则

- **数组**：`["kline", symbol, period]`
- 同一资源的 key 前缀一致，便于按前缀失效
- 参数顺序固定，不要乱

## useMutation 模板

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createStrategy } from "@/api/strategy";

const qc = useQueryClient();
const m = useMutation({
  mutationFn: createStrategy,
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["strategy", "list"] });
    message.success("已创建");
  },
});

<Button loading={m.isPending} onClick={() => m.mutate({ name, symbol })}>提交</Button>
```

## 缓存失效

```tsx
qc.invalidateQueries({ queryKey: ["strategy"] });            // 前缀匹配所有 strategy*
qc.invalidateQueries({ queryKey: ["strategy", "list"], exact: true });  // 精确
qc.setQueryData(["strategy", id], (old) => ({ ...old, name: "new" }));  // 乐观更新
```

## 常用配置

```tsx
useQuery({
  ...,
  refetchOnWindowFocus: false,    // 默认 true，切回页面会重拉
  refetchInterval: 5_000,         // 轮询
  refetchIntervalInBackground: false,
  retry: 3,
  gcTime: 5 * 60 * 1000,          // 缓存保留 5 分钟（v5: gcTime, 旧名 cacheTime）
});
```

## 与 WebSocket 配合

```tsx
useEffect(() => {
  const ws = new WebSocket("/ws/quote");
  ws.onmessage = (e) => {
    const tick = JSON.parse(e.data);
    qc.setQueryData(["quote", tick.symbol], tick);    // 推送到缓存
  };
  return () => ws.close();
}, [qc]);
```

## DevTools（开发期可选）

```tsx
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
<ReactQueryDevtools initialIsOpen={false} />
```

需要 `pnpm add -D @tanstack/react-query-devtools`。

## 错误处理

axios 拦截器已统一弹 message。组件层用 `error` 字段做 UI 状态：

```tsx
if (error) return <Empty description="加载失败" />;
```

## 禁止

- ❌ 在 useEffect 里 fetch 然后 useState（用 useQuery）
- ❌ 用 React Query 存客户端 UI 状态（用 Zustand / useState）
- ❌ queryKey 拼字符串（用数组）
- ❌ 在组件外手动调 queryClient（要从 hook 里取）
