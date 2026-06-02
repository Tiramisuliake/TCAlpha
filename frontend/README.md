# TCAlpha Frontend

React 19 + TypeScript 5 + Vite 7 + Ant Design 5 + TailwindCSS 4 + Zustand + React Query + ECharts + lightweight-charts

## 启动

```bash
pnpm install
pnpm dev      # http://localhost:5173
pnpm build
pnpm exec tsc --noEmit
```

后端 API 代理目标由 `.dev-port` 决定（`backend/run.py` 启动时自动写入；gitignored）。**不再固定 8000**。
锁定端口：`BACKEND_PORT=8000 pnpm dev`，或在 `.run/Frontend.run.xml` 加环境变量。

## 目录约定

```
src/
├── main.tsx           应用入口（ConfigProvider + <AntApp> + FeedbackBridge + Router）
├── App.tsx            Shell + 路由表 + 侧栏按 useAuthStore.has(perm) 过滤
├── pages/             每页一个目录
│   ├── Dashboard / Chart / Strategy / Backtest / Trade / Data / AI / Notify
│   ├── Login          登录页
│   └── System/        v0.7.2+：Users / Roles 用户角色管理
├── components/
│   ├── PermButton     v0.7.6+ 写按钮权限守卫
│   ├── FeedbackBridge AntD <App> 注入全局 feedback
│   ├── PageScaffold
│   └── WorkspaceTabs/ 多 tab 导航
├── api/
│   ├── client.ts      ★ axios 实例 + 401 自动 refresh
│   ├── auth.ts        裸 axios，防 401-on-401 死循环
│   ├── streamClient.ts 带刷新的 fetch / SSE
│   └── market / strategy / backtest / sim / ai / notify / system / ...
├── store/
│   ├── useAuthStore   ★ access token + me + has/hasAny/scope
│   └── useWorkspaceStore
├── hooks/             useWebSocket / useSSE 等
├── types/index.ts     全局 TypeScript 接口
├── utils/feedback.ts  全局 message / notification holder
└── styles/index.css   TailwindCSS 4
```

## 规范

- **路径导入用 `@/` 别名**，禁止 `../../`
- **API 调用走 `@/api/*.ts`**，禁止组件里裸 `axios`
- **服务端状态用 React Query**（`useQuery` / `useMutation`），不要塞 Zustand 再手动同步
- **客户端 UI 状态用 Zustand**（主题 / 侧栏 / 登录态）
- **UI 优先 Ant Design**；布局用 Tailwind class
- **写按钮加权限守卫**：用 `<PermButton perm="xxx">`，缺权限会 disabled + Tooltip
  - 纯破坏性操作（删除）用 `hideOnDenied`
  - super 用户自动绕过
- **toast 用 hook 版**：`const { message } = App.useApp()`，避免静态 `message.error()` 在 React 19 严格模式被吞
  - 非组件场景（axios 拦截器等）用 `@/utils/feedback`

## 鉴权

- 登录 → access token 存 `useAuthStore.accessToken`（内存，关 tab 即失效）
- refresh token 由后端写 HttpOnly cookie（js 读不到）
- `client.ts` 自动给请求加 `Authorization: Bearer <access>`
- 401 自动 refresh 重试一次，失败跳 `/login`
- `useAuthStore.has(perm)` / `hasAny(...)` / `scope()` 给 UI 做权限判断
