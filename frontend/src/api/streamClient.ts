import { authHeader, useAuthStore } from "@/store/useAuthStore";
import { feedback } from "@/utils/feedback";

function redirectToLogin(): void {
  feedback.error("登录已失效，请重新登录");
  if (!location.pathname.startsWith("/login")) {
    location.assign(`/login?from=${encodeURIComponent(location.pathname)}`);
  }
}

export async function fetchWithAuthRefresh(
  input: string,
  init: () => RequestInit,
): Promise<Response> {
  const first = await fetch(input, init());
  if (first.status !== 401) {
    return first;
  }

  const ok = await useAuthStore.getState().refresh();
  if (!ok) {
    redirectToLogin();
    return first;
  }

  return fetch(input, init());
}

export function streamHeaders(extra?: HeadersInit): HeadersInit {
  return {
    ...extra,
    ...authHeader(),
  };
}
