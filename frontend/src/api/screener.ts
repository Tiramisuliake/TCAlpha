import { api } from "./client";
import type {
  FactorICResult,
  FactorICSummary,
  FactorPortfolioResult,
  FactorScreenFilters,
  FactorWalkforwardResult,
  FactorWeights,
  LimitUpPremiumResult,
  PatternStatsResult,
  PortfolioRecord,
  PortfolioSweepCell,
  ScreenFilters,
  ScreenResult,
  ShortTermFilters,
} from "@/types";

export const runScreen = (filters: ScreenFilters) =>
  api.post<ScreenResult>("/screener/run", filters).then((r) => r.data);

export const runFactorScreen = (filters: FactorScreenFilters) =>
  api.post<ScreenResult>("/screener/factor", filters).then((r) => r.data);

export const runFactorIC = (payload: {
  factor: string;
  hold_days?: number;
  lookback?: number;
  sample_points?: number;
  max_scan?: number;
}) => api.post<FactorICResult>("/screener/factor-ic", payload).then((r) => r.data);

export const runFactorICAll = (payload: {
  hold_days?: number;
  lookback?: number;
  sample_points?: number;
  max_scan?: number;
}) => api.post<FactorICSummary[]>("/screener/factor-ic-all", payload).then((r) => r.data);

export const runFactorPortfolio = (payload: {
  weights: FactorWeights;
  top_n?: number;
  rebalance_days?: number;
  lookback?: number;
  max_scan?: number;
}) => api.post<FactorPortfolioResult>("/screener/factor-portfolio", payload).then((r) => r.data);

export const runFactorPortfolioSweep = (payload: {
  weights: FactorWeights;
  top_n_list: number[];
  rebalance_list: number[];
  lookback?: number;
  max_scan?: number;
}) =>
  api
    .post<PortfolioSweepCell[]>("/screener/factor-portfolio-sweep", payload)
    .then((r) => r.data);

export const runFactorWalkforward = (payload: {
  weights: FactorWeights;
  top_n?: number;
  rebalance_days?: number;
  lookback?: number;
  oos_ratio?: number;
}) =>
  api
    .post<FactorWalkforwardResult>("/screener/factor-portfolio/walkforward", payload)
    .then((r) => r.data);

export const savePortfolioRecord = (payload: {
  name: string;
  kind?: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
}) =>
  api.post<PortfolioRecord>("/screener/factor-portfolio/records", payload).then((r) => r.data);

export const listPortfolioRecords = () =>
  api.get<PortfolioRecord[]>("/screener/factor-portfolio/records").then((r) => r.data);

export const deletePortfolioRecord = (id: number) =>
  api.delete(`/screener/factor-portfolio/records/${id}`).then((r) => r.data);

/** 导出组合回测自包含 HTML 报告（重跑回测 + 渲染，blob 触发浏览器保存）。 */
export const downloadPortfolioReport = async (payload: {
  weights: FactorWeights;
  top_n?: number;
  rebalance_days?: number;
  lookback?: number;
}) => {
  const r = await api.post<Blob>("/screener/factor-portfolio/report", payload, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tcalpha_portfolio_${Date.now()}.html`;
  a.click();
  URL.revokeObjectURL(url);
};

export const runShortTerm = (filters: ShortTermFilters) =>
  api.post<ScreenResult>("/screener/short-term", filters).then((r) => r.data);

export const runResonance = (filters: { min_patterns: number; exclude_st?: boolean; price_min?: number; price_max?: number; limit?: number }) =>
  api.post<ScreenResult>("/screener/resonance", filters).then((r) => r.data);

export const runLimitUpPremium = (payload: { symbol?: string; lookback?: number }) =>
  api.post<LimitUpPremiumResult>("/screener/limit-up-premium", payload).then((r) => r.data);

export const matchPatterns = (symbols: string[]) =>
  api.post<Record<string, string[]>>("/screener/match-patterns", { symbols }).then((r) => r.data);

export const runPatternStats = (payload: { pattern: string; hold_days?: number; lookback?: number }) =>
  api.post<PatternStatsResult>("/screener/pattern-stats", payload).then((r) => r.data);

export const runPatternStatsAll = (payload: { hold_days?: number; lookback?: number }) =>
  api.post<PatternStatsResult[]>("/screener/pattern-stats-all", payload).then((r) => r.data);
