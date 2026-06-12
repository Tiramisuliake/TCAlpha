import { api } from "./client";
import type { BacktestStatus, BacktestSubmit, BacktestTrade, SweepStatus, SweepSubmit } from "@/types";

export const submitBacktest = (payload: BacktestSubmit) =>
  api.post<BacktestStatus>("/backtest/submit", payload).then((r) => r.data);

export const getBacktestStatus = (jobId: number) =>
  api.get<BacktestStatus>(`/backtest/${jobId}`).then((r) => r.data);

export const listBacktests = () =>
  api.get<BacktestStatus[]>("/backtest/list").then((r) => r.data);

export const getBacktestTrades = (jobId: number) =>
  api.get<BacktestTrade[]>(`/backtest/${jobId}/trades`).then((r) => r.data);

/** 下载自包含 HTML 回测报告（带鉴权走 axios blob，再触发浏览器保存）。 */
export const downloadReport = async (jobId: number) => {
  const r = await api.get<Blob>(`/backtest/${jobId}/report`, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tcalpha_backtest_${jobId}.html`;
  a.click();
  URL.revokeObjectURL(url);
};

export const submitSweep = (payload: SweepSubmit) =>
  api.post<SweepStatus>("/backtest/sweep/submit", payload).then((r) => r.data);

export const getSweepStatus = (jobId: number) =>
  api.get<SweepStatus>(`/backtest/sweep/${jobId}`).then((r) => r.data);

export const listSweeps = () =>
  api.get<SweepStatus[]>("/backtest/sweep/list").then((r) => r.data);
