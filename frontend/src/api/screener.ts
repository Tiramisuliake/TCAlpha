import { api } from "./client";
import type { ScreenFilters, ScreenResult } from "@/types";

export const runScreen = (filters: ScreenFilters) =>
  api.post<ScreenResult>("/screener/run", filters).then((r) => r.data);
