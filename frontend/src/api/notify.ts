import { api } from "./client";

export interface NotifyRule {
  id: number;
  user_id: number;
  name: string;
  match_types: string[];
  match_filters: Record<string, unknown>;
  channels: string[];
  feishu_webhook: string;
  feishu_secret: string;
  quiet_hours: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotifyRuleInput {
  name: string;
  match_types: string[];
  match_filters?: Record<string, unknown>;
  channels: string[];
  feishu_webhook?: string;
  feishu_secret?: string;
  quiet_hours?: string;
  enabled?: boolean;
}

export interface NotifyLog {
  id: number;
  rule_id: number | null;
  event_type: string;
  channel: string;
  payload: Record<string, unknown>;
  success: boolean;
  error_msg: string;
  created_at: string;
}

export interface EventTypeMeta {
  type: string;
  desc: string;
}

export interface NotifyMeta {
  event_types: EventTypeMeta[];
  channels: string[];
}

export interface TestPushRequest {
  rule_id?: number;
  feishu_webhook?: string;
  feishu_secret?: string;
  content?: string;
}

export const listRules = () =>
  api.get<NotifyRule[]>("/notify/rules").then((r) => r.data);

export const createRule = (payload: NotifyRuleInput) =>
  api.post<NotifyRule>("/notify/rules", payload).then((r) => r.data);

export const updateRule = (id: number, payload: NotifyRuleInput) =>
  api.put<NotifyRule>(`/notify/rules/${id}`, payload).then((r) => r.data);

export const deleteRule = (id: number) =>
  api.delete(`/notify/rules/${id}`).then((r) => r.data);

export const listLogs = (limit = 100) =>
  api.get<NotifyLog[]>("/notify/logs", { params: { limit } }).then((r) => r.data);

export const getMeta = () =>
  api.get<NotifyMeta>("/notify/event-types").then((r) => r.data);

export const testPush = (payload: TestPushRequest) =>
  api
    .post<{ success: boolean; error: string | null }>("/notify/test", payload)
    .then((r) => r.data);
