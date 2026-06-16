import { api } from "./client";
import type { AccountOut, EquityCurveOut, PlaceOrderRequest, PositionSummary, SimOrder } from "@/types";

export const listOrders = (strategyId?: number, limit = 50) =>
  api
    .get<SimOrder[]>("/sim/orders", { params: { strategy_id: strategyId, limit } })
    .then((r) => r.data);

export const placeOrder = (payload: PlaceOrderRequest) =>
  api.post<SimOrder>("/sim/orders", payload).then((r) => r.data);

export const cancelOrder = (orderId: number) =>
  api.post<SimOrder>(`/sim/orders/${orderId}/cancel`).then((r) => r.data);

export const listPositions = () =>
  api.get<PositionSummary[]>("/sim/positions").then((r) => r.data);

export const getAccount = () =>
  api.get<AccountOut>("/sim/account").then((r) => r.data);

export const resetAccount = () =>
  api.post<AccountOut>("/sim/account/reset").then((r) => r.data);

export const getEquityCurve = (days = 180) =>
  api.get<EquityCurveOut>("/sim/equity-curve", { params: { days } }).then((r) => r.data);

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
