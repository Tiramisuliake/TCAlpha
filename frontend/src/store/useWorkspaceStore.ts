import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type WorkspaceRouteKey =
  | "dashboard"
  | "chart"
  | "strategy"
  | "backtest"
  | "trade"
  | "data"
  | "ai"
  | "notify"
  | "system-users"
  | "system-roles";

export interface WorkspaceRouteMeta {
  path: string;
  title: string;
  closable: boolean;
}

export interface WorkspaceTab extends WorkspaceRouteMeta {
  key: WorkspaceRouteKey;
}

export const WORKSPACE_ROUTES: Record<WorkspaceRouteKey, WorkspaceRouteMeta> = {
  dashboard: { path: "/", title: "仪表盘", closable: false },
  chart: { path: "/chart", title: "K 线分析", closable: true },
  strategy: { path: "/strategy", title: "策略管理", closable: true },
  backtest: { path: "/backtest", title: "回测", closable: true },
  trade: { path: "/trade", title: "模拟交易", closable: true },
  data: { path: "/data", title: "数据管理", closable: true },
  ai: { path: "/ai", title: "AI 助手", closable: true },
  notify: { path: "/notify", title: "通知中心", closable: true },
  "system-users": { path: "/system/users", title: "用户管理", closable: true },
  "system-roles": { path: "/system/roles", title: "角色管理", closable: true },
};

const DEFAULT_TABS: WorkspaceTab[] = [
  { key: "dashboard", ...WORKSPACE_ROUTES.dashboard },
];

interface WorkspaceState {
  tabs: WorkspaceTab[];
  activeKey: WorkspaceRouteKey;
  openTab: (key: WorkspaceRouteKey) => void;
  closeTab: (key: WorkspaceRouteKey) => WorkspaceRouteKey;
  setActive: (key: WorkspaceRouteKey) => void;
  reorder: (fromKey: WorkspaceRouteKey, toKey: WorkspaceRouteKey) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      tabs: DEFAULT_TABS,
      activeKey: "dashboard",
      openTab: (key) => {
        const tabs = get().tabs;
        if (tabs.some((t) => t.key === key)) {
          set({ activeKey: key });
          return;
        }
        const meta = WORKSPACE_ROUTES[key];
        set({
          tabs: [...tabs, { key, ...meta }],
          activeKey: key,
        });
      },
      closeTab: (key) => {
        const { tabs, activeKey } = get();
        const target = tabs.find((t) => t.key === key);
        if (!target || !target.closable) return activeKey;
        const idx = tabs.findIndex((t) => t.key === key);
        const remaining = tabs.filter((t) => t.key !== key);
        let nextActive = activeKey;
        if (activeKey === key) {
          const leftIdx = Math.max(0, idx - 1);
          nextActive = remaining[leftIdx]?.key ?? "dashboard";
        }
        set({ tabs: remaining, activeKey: nextActive });
        return nextActive;
      },
      setActive: (key) => set({ activeKey: key }),
      reorder: (fromKey, toKey) => {
        const tabs = get().tabs;
        const fromIdx = tabs.findIndex((t) => t.key === fromKey);
        const toIdx = tabs.findIndex((t) => t.key === toKey);
        if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return;
        const next = [...tabs];
        const [moved] = next.splice(fromIdx, 1);
        next.splice(toIdx, 0, moved);
        set({ tabs: next });
      },
    }),
    {
      name: "tcalpha.workspace",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ tabs: s.tabs, activeKey: s.activeKey }),
    }
  )
);

export function findRouteByPath(pathname: string): WorkspaceRouteKey | null {
  if (pathname === "/" || pathname === "") return "dashboard";
  const entries = Object.entries(WORKSPACE_ROUTES) as [
    WorkspaceRouteKey,
    WorkspaceRouteMeta,
  ][];
  for (const [key, meta] of entries) {
    if (meta.path !== "/" && pathname.startsWith(meta.path)) {
      return key;
    }
  }
  return null;
}
