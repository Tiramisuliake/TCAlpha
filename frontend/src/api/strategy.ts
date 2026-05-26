import { api } from "./client";
import type { StrategyClassInfo, StrategyConfig, StrategyCreate } from "@/types";

export const getStrategyClasses = () =>
  api.get<{ classes: StrategyClassInfo[] }>("/strategy/classes").then((r) => r.data.classes);

export const getStrategies = () =>
  api.get<StrategyConfig[]>("/strategy/list").then((r) => r.data);

export const createStrategy = (payload: StrategyCreate) =>
  api.post<StrategyConfig>("/strategy", payload).then((r) => r.data);

export const updateStrategy = (id: number, payload: StrategyCreate) =>
  api.put<StrategyConfig>(`/strategy/${id}`, payload).then((r) => r.data);

export const deleteStrategy = (id: number) =>
  api.delete(`/strategy/${id}`).then((r) => r.data);
