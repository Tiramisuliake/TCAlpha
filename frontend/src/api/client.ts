import axios from "axios";
import { message } from "antd";
import { authHeader, useAuthStore } from "@/store/useAuthStore";

export const api = axios.create({
  baseURL: "/api",
  timeout: 30_000,
});

// 注入 Basic Auth header（若已登录）
api.interceptors.request.use((cfg) => {
  const h = authHeader();
  if (h.Authorization && cfg.headers) {
    cfg.headers.set
      ? cfg.headers.set("Authorization", h.Authorization)
      : ((cfg.headers as Record<string, string>).Authorization = h.Authorization);
  }
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err?.response?.status;
    if (status === 401) {
      // 凭证失效：清状态触发跳登录
      useAuthStore.getState().logout();
      message.error("登录已失效，请重新登录");
      if (!location.pathname.startsWith("/login")) {
        location.assign(`/login?from=${encodeURIComponent(location.pathname)}`);
      }
      return Promise.reject(err);
    }
    const msg = err?.response?.data?.detail ?? err?.message ?? "请求失败";
    message.error(String(msg));
    return Promise.reject(err);
  }
);

// /health 不在 /api 前缀下，单独导出
export const root = axios.create({ baseURL: "/", timeout: 10_000 });
