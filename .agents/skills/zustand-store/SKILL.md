---
name: zustand-store
description: Zustand 全局状态 / persist / slice 拆分 / 选择器。触发词：Zustand、store、全局状态、共享状态、状态管理、persist、selector
---

# Zustand 状态管理

## 何时用 Zustand

- 跨页面共享的 UI 状态（当前选中股票、主题、侧栏折叠）
- 客户端持久化（localStorage 缓存）
- 不是服务器数据（服务器数据用 React Query）

## 基础模板

```ts
// src/store/auth.ts
import { create } from "zustand";

interface AuthState {
  userId: number;
  token: string | null;
  setToken: (t: string | null) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  userId: 1,
  token: null,
  setToken: (t) => set({ token: t }),
  logout: () => set({ token: null }),
}));
```

组件里：

```tsx
const token = useAuth((s) => s.token);          // 只订阅 token，其他字段变不重渲染
const setToken = useAuth((s) => s.setToken);
```

**永远用 selector**，不要 `const state = useAuth()`，否则任何字段变都重渲染。

## persist 中间件

```ts
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface ChartPref {
  period: string;
  showVolume: boolean;
  setPeriod: (p: string) => void;
}

export const useChartPref = create<ChartPref>()(
  persist(
    (set) => ({
      period: "1d",
      showVolume: true,
      setPeriod: (period) => set({ period }),
    }),
    {
      name: "tcalpha:chart-pref",
      storage: createJSONStorage(() => localStorage),
    }
  )
);
```

## slice 拆分（store 大了再用）

```ts
import { create, StateCreator } from "zustand";

const createAuthSlice: StateCreator<AuthSlice> = (set) => ({ ... });
const createUiSlice: StateCreator<UiSlice> = (set) => ({ ... });

export const useApp = create<AuthSlice & UiSlice>()((...a) => ({
  ...createAuthSlice(...a),
  ...createUiSlice(...a),
}));
```

但**单 store 文件 < 150 行就别拆**。

## 与 React Query 配合

| 数据来源 | 工具 |
|---|---|
| 后端数据 | React Query（自动 cache + refetch） |
| URL 状态 | useSearchParams |
| 用户偏好 | Zustand + persist |
| 一次性 UI | useState |

不要把后端数据塞 Zustand 再手动同步，徒增复杂度。

## 调试

```ts
import { devtools } from "zustand/middleware";

export const useAuth = create<AuthState>()(
  devtools((set) => ({ ... }), { name: "auth" })
);
```

Redux DevTools 浏览器扩展直接能看。

## 命名

- store 文件：`src/store/<name>.ts`
- 导出 hook：`use<Name>`（如 `useAuth` / `useChartPref`）

## 禁止

- ❌ store 里调 API（API 在 src/api/，store 只接结果）
- ❌ 全部状态塞一个巨型 store
- ❌ 没用 selector 导致整组件树重渲染
- ❌ persist 存敏感数据（token 短期可，长期用 cookie httpOnly）
