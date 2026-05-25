import axios from "axios";
import { message } from "antd";

export const api = axios.create({
  baseURL: "/api",
  timeout: 30_000,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const msg = err?.response?.data?.detail ?? err?.message ?? "请求失败";
    message.error(String(msg));
    return Promise.reject(err);
  }
);

// /health 不在 /api 前缀下，单独导出
export const root = axios.create({ baseURL: "/", timeout: 10_000 });
