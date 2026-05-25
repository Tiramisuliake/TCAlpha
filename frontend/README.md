# TCAlpha Frontend

React 19 + TypeScript 5 + Vite 7 + Ant Design 5 + TailwindCSS 4 + Zustand + ECharts + lightweight-charts

```bash
pnpm install
pnpm dev      # http://localhost:5173 （已配代理到后端 :8000）
pnpm build
```

## 目录约定

```
src/
├── main.tsx          应用入口（Router / AntD / Query / Tailwind）
├── App.tsx           Shell + 路由表
├── pages/            每页一个目录（Dashboard / Chart / Strategy / Backtest / Data / AI）
├── components/       通用组件
├── api/              axios 封装 + 各模块 API
├── store/            Zustand store
├── hooks/            自定义 hooks（useWebSocket / useSSE）
├── types/            集中类型定义
└── styles/           全局 CSS（TailwindCSS）
```

## 规范

- 路径导入用 `@/` 别名
- 所有 invoke 用 `api` (axios)，禁止组件里 fetch
- 服务器状态用 React Query；客户端 UI 状态用 Zustand
- UI 优先 Ant Design 组件；布局用 Tailwind
