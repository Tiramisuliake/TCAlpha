import { api } from "./client";
import type {
  LimitUpPremiumResult,
  PatternStatsResult,
  ScreenFilters,
  ScreenResult,
  ShortTermFilters,
} from "@/types";

export const runScreen = (filters: ScreenFilters) =>
  api.post<ScreenResult>("/screener/run", filters).then((r) => r.data);

export const runShortTerm = (filters: ShortTermFilters) =>
  api.post<ScreenResult>("/screener/short-term", filters).then((r) => r.data);

export const runLimitUpPremium = (payload: { symbol?: string; lookback?: number }) =>
  api.post<LimitUpPremiumResult>("/screener/limit-up-premium", payload).then((r) => r.data);

export const matchPatterns = (symbols: string[]) =>
  api.post<Record<string, string[]>>("/screener/match-patterns", { symbols }).then((r) => r.data);

export const runPatternStats = (payload: { pattern: string; hold_days?: number; lookback?: number }) =>
  api.post<PatternStatsResult>("/screener/pattern-stats", payload).then((r) => r.data);
