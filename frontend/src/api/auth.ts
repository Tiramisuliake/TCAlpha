/**
 * Auth API（Phase 7 v0.7.0b）。
 *
 * 这一层是裸 axios（不走 client.ts 拦截器），避免 401-on-401 死循环。
 * - login / refresh / logout 都必须 withCredentials，刷新 cookie 才会带回
 * - 错误统一抛 Error，由调用方（store）处理
 */
import axios from "axios";
import type { MeResponse, TokenResponse } from "@/types";

const raw = axios.create({
  baseURL: "/api/auth",
  timeout: 15_000,
  withCredentials: true,
});

export async function apiLogin(
  username: string,
  password: string,
): Promise<TokenResponse> {
  const r = await raw.post<TokenResponse>("/login", { username, password });
  return r.data;
}

export async function apiRefresh(): Promise<TokenResponse> {
  const r = await raw.post<TokenResponse>("/refresh");
  return r.data;
}

export async function apiLogout(accessToken: string | null): Promise<void> {
  // 带 access 让后端把它也拉黑（即时失效，不等 15min）
  const headers = accessToken
    ? { Authorization: `Bearer ${accessToken}` }
    : undefined;
  await raw.post("/logout", null, { headers });
}

export async function apiMe(accessToken: string): Promise<MeResponse> {
  const r = await raw.get<MeResponse>("/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return r.data;
}
