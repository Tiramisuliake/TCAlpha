import { api } from "./client";
import type {
  DataHealth,
  KlineResponse,
  LimitUpLadder,
  MarketSentiment,
  NorthFlow,
  PatternMarker,
  SentimentPoint,
  SymbolListResponse,
} from "@/types";

export interface SymbolsParams {
  search?: string;
  exchange?: string;
  limit?: number;
  offset?: number;
}

export const getSymbols = (params: SymbolsParams = {}) =>
  api.get<SymbolListResponse>("/market/symbols", { params }).then((r) => r.data);

export const getKline = (symbol: string, period = "1d", limit = 300) =>
  api.get<KlineResponse>(`/market/kline/${symbol}`, { params: { period, limit } }).then((r) => r.data);

export const getKlinePatterns = (symbol: string, lookback = 250) =>
  api.get<PatternMarker[]>(`/market/kline/${symbol}/patterns`, { params: { lookback } }).then((r) => r.data);

export const triggerDownload = (symbol: string, period = "1d") =>
  api.post(`/market/kline/${symbol}/download`, null, { params: { period } }).then((r) => r.data);

export const refreshSymbols = () =>
  api.post<{ task_id: string; message: string }>("/market/symbols/refresh").then((r) => r.data);

export const getDataHealth = () =>
  api.get<DataHealth>("/data/health").then((r) => r.data);

export const getSentiment = () =>
  api.get<MarketSentiment>("/market/sentiment").then((r) => r.data);

export const getSentimentHistory = (days = 120) =>
  api
    .get<SentimentPoint[]>("/market/sentiment/history", { params: { days } })
    .then((r) => r.data);

export const getLimitUpLadder = () =>
  api.get<LimitUpLadder>("/market/limit-up-ladder").then((r) => r.data);

export const getNorthFlow = (days = 60) =>
  api.get<NorthFlow>("/market/north-flow", { params: { days } }).then((r) => r.data);
