import { api } from "./client";
import type { SimOrder } from "@/types";

export const listOrders = (strategyId?: number, limit = 50) =>
  api
    .get<SimOrder[]>("/sim/orders", { params: { strategy_id: strategyId, limit } })
    .then((r) => r.data);

export const getPosition = (symbol: string) =>
  api
    .get<{ symbol: string; net_position: number }>(`/sim/position/${symbol}`)
    .then((r) => r.data);

export const startStrategy = (strategyId: number) =>
  api.post<{ task_id: string; status: string }>(`/strategy/${strategyId}/start`).then((r) => r.data);

export const stopStrategy = (strategyId: number) =>
  api.post<{ status: string }>(`/strategy/${strategyId}/stop`).then((r) => r.data);

export const getStrategyRunning = (strategyId: number) =>
  api.get<{ running: boolean }>(`/strategy/${strategyId}/running`).then((r) => r.data);
