/**
 * JWT 登录态（Phase 7 v0.7.0b）。
 *
 * 安全模型：
 * - access token 仅存内存（关 tab 即丢，xss 拿不到）
 * - refresh token 由后端写 HttpOnly cookie（js 读不到），SameSite=Strict 防 CSRF
 * - 启动 / 401 → 尝试 refresh：用 cookie 静默恢复登录态
 *
 * 为兼容 v0.6.0 / Phase 6 中间件期的 WebSocket 端点，仍提供 wsUrl(path)：
 * 把 access token 拼到 query，让 WS 路由可以解析（如果后端 BasicAuthMiddleware
 * 关闭，则 token query 不会被中间件拦，业务路由按需自取）。
 */
import { create } from "zustand";
import { apiLogin, apiLogout, apiMe, apiRefresh } from "@/api/auth";
import type { DataScope, MeResponse } from "@/types";

interface AuthState {
  accessToken: string | null;
  userId: number | null;
  me: MeResponse | null;
  // 启动 / silent refresh 期间标记：用于 RequireAuth 等待 cookie 验证完成再决定跳转
  bootstrapping: boolean;

  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<boolean>;
  loadMe: () => Promise<void>;
  bootstrap: () => Promise<void>;
  setAccessToken: (t: string | null, userId?: number | null) => void;

  has: (perm: string) => boolean;
  hasAny: (...perms: string[]) => boolean;
  scope: () => DataScope;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  userId: null,
  me: null,
  bootstrapping: true,

  setAccessToken: (accessToken, userId = null) =>
    set({ accessToken, userId }),

  login: async (username, password) => {
    const r = await apiLogin(username, password);
    set({ accessToken: r.access_token, userId: r.user_id });
    await get().loadMe();
  },

  logout: async () => {
    const t = get().accessToken;
    try {
      await apiLogout(t);
    } catch {
      // 服务端可能已下线 / 网络故障；本地状态仍要清
    }
    set({ accessToken: null, userId: null, me: null });
  },

  refresh: async () => {
    try {
      const r = await apiRefresh();
      set({ accessToken: r.access_token, userId: r.user_id });
      return true;
    } catch {
      set({ accessToken: null, userId: null, me: null });
      return false;
    }
  },

  loadMe: async () => {
    const t = get().accessToken;
    if (!t) return;
    try {
      const me = await apiMe(t);
      set({ me });
    } catch {
      // 401 会在 client 拦截器里触发刷新；这里静默
    }
  },

  bootstrap: async () => {
    set({ bootstrapping: true });
    const ok = await get().refresh();
    if (ok) {
      await get().loadMe();
    }
    set({ bootstrapping: false });
  },

  has: (perm) => {
    const me = get().me;
    if (!me) return false;
    return me.is_super || me.permissions.includes(perm);
  },
  hasAny: (...perms) => {
    const me = get().me;
    if (!me) return false;
    if (me.is_super) return true;
    return perms.some((p) => me.permissions.includes(p));
  },
  scope: () => get().me?.data_scope ?? "self",
}));

// ── 非 Hook 读取（axios / fetch / WS 内部用）────────────────────────
export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken;
}

export function authHeader(): Record<string, string> {
  const t = getAccessToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** 构造 WS URL：把 access token 拼到 query。 */
export function wsUrl(path: string): string {
  const token = getAccessToken();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const base = `${proto}//${location.host}${path}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}
