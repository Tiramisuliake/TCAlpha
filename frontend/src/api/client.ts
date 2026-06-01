/**
 * 统一 axios 客户端（Phase 7 v0.7.0b）。
 *
 * 拦截器流程：
 * - request：注入 Bearer access token（若有）
 * - response 401：尝试 refresh（共享 in-flight Promise，避免并发风暴）
 *   - 成功 → 用新 access 重试原请求一次（仅一次，防死循环）
 *   - 失败 → 清状态 + 跳 /login
 */
import axios, {
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";
import { authHeader, useAuthStore } from "@/store/useAuthStore";
import { feedback } from "@/utils/feedback";

// 扩展 InternalAxiosRequestConfig，加一个内部标志位
interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

export const api = axios.create({
  baseURL: "/api",
  timeout: 30_000,
  withCredentials: true, // refresh cookie 需要随请求带（同源也声明明确）
});

api.interceptors.request.use((cfg) => {
  const h = authHeader();
  if (h.Authorization && cfg.headers) {
    if (cfg.headers.set) {
      cfg.headers.set("Authorization", h.Authorization);
    } else {
      (cfg.headers as Record<string, string>).Authorization = h.Authorization;
    }
  }
  return cfg;
});

// in-flight refresh：所有并发 401 共享一个刷新请求
let refreshPromise: Promise<boolean> | null = null;
function sharedRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = useAuthStore
      .getState()
      .refresh()
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function isAuthRoute(url: string | undefined): boolean {
  if (!url) return false;
  // 防 /api/auth/refresh / /api/auth/login 本身 401 时再次走 refresh
  return url.includes("/auth/refresh") || url.includes("/auth/login");
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err?.response?.status;
    const cfg = err?.config as RetryConfig | undefined;

    if (status === 401 && cfg && !cfg._retry && !isAuthRoute(cfg.url)) {
      cfg._retry = true;
      const ok = await sharedRefresh();
      if (ok) {
        // 用新 token 重试一次
        const h = authHeader();
        if (h.Authorization && cfg.headers) {
          if (cfg.headers.set) {
            cfg.headers.set("Authorization", h.Authorization);
          } else {
            (cfg.headers as Record<string, string>).Authorization = h.Authorization;
          }
        }
        return api.request(cfg as AxiosRequestConfig);
      }
      // refresh 失败 → 走未授权流程
      feedback.error("登录已失效，请重新登录");
      if (!location.pathname.startsWith("/login")) {
        location.assign(`/login?from=${encodeURIComponent(location.pathname)}`);
      }
      return Promise.reject(err);
    }

    const msg = err?.response?.data?.detail ?? err?.message ?? "请求失败";
    feedback.error(String(msg));
    return Promise.reject(err);
  },
);

// /health 不在 /api 前缀下，单独导出
export const root = axios.create({ baseURL: "/", timeout: 10_000 });
