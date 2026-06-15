import { api } from "./client";
import type { ScreenFilters, ScreenResult, ShortTermFilters } from "@/types";

export const runScreen = (filters: ScreenFilters) =>
  api.post<ScreenResult>("/screener/run", filters).then((r) => r.data);

export const runShortTerm = (filters: ShortTermFilters) =>
  api.post<ScreenResult>("/screener/short-term", filters).then((r) => r.data);
