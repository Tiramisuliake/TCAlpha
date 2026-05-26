import { api } from "./client";
import type { BacktestStatus, BacktestSubmit, BacktestTrade } from "@/types";

export const submitBacktest = (payload: BacktestSubmit) =>
  api.post<BacktestStatus>("/backtest/submit", payload).then((r) => r.data);

export const getBacktestStatus = (jobId: number) =>
  api.get<BacktestStatus>(`/backtest/${jobId}`).then((r) => r.data);

export const listBacktests = () =>
  api.get<BacktestStatus[]>("/backtest/list").then((r) => r.data);

export const getBacktestTrades = (jobId: number) =>
  api.get<BacktestTrade[]>(`/backtest/${jobId}/trades`).then((r) => r.data);
