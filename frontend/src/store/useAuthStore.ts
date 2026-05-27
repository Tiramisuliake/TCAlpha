/**
 * Basic Auth 凭证存储（Phase 6 v0.6.0）。
 *
 * 用 sessionStorage 而非 localStorage：关浏览器即失效，降低凭证泄漏面。
 * 多 tab 通过 storage 事件也不广播，符合"单设备会话"语义。
 */
import { create } from "zustand";

const KEY = "tcalpha.auth";

interface AuthState {
  token: string | null; // base64(user:pass)
  username: string | null;
  login: (username: string, password: string) => void;
  logout: () => void;
  hydrate: () => void;
}

function readSession(): { token: string; username: string } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeSession(token: string, username: string) {
  sessionStorage.setItem(KEY, JSON.stringify({ token, username }));
}

function clearSession() {
  sessionStorage.removeItem(KEY);
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  username: null,
  hydrate: () => {
    const s = readSession();
    if (s) set({ token: s.token, username: s.username });
  },
  login: (username, password) => {
    const token = btoa(`${username}:${password}`);
    writeSession(token, username);
    set({ token, username });
  },
  logout: () => {
    clearSession();
    set({ token: null, username: null });
  },
}));

/** 同步读取（非 hook）：axios / fetch / WS 内部用。 */
export function getAuthToken(): string | null {
  return readSession()?.token ?? null;
}

export function authHeader(): Record<string, string> {
  const t = getAuthToken();
  return t ? { Authorization: `Basic ${t}` } : {};
}

/** 构造 WS URL：把 token 拼到 query。 */
export function wsUrl(path: string): string {
  const token = getAuthToken();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const base = `${proto}//${location.host}${path}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}
