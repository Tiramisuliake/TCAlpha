import { api } from "./client";

export type AlertLevel = "info" | "warn" | "danger";

export interface AiAlert {
  id: number;
  user_id: number;
  symbol: string;
  level: AlertLevel;
  signal: string;
  reason: string;
  snapshot: Record<string, unknown>;
  acked: boolean;
  created_at: string;
}

export interface ListAlertsParams {
  level?: AlertLevel;
  symbol?: string;
  only_unacked?: boolean;
  limit?: number;
}

export const listAlerts = (params: ListAlertsParams = {}) =>
  api.get<AiAlert[]>("/ai-alerts", { params }).then((r) => r.data);

export const ackAlert = (id: number) =>
  api.post(`/ai-alerts/${id}/ack`).then((r) => r.data);

export const triggerWatch = (symbol: string) =>
  api
    .post<{ task_id: string; status: string }>(
      `/ai-alerts/watch/${encodeURIComponent(symbol)}`,
    )
    .then((r) => r.data);
