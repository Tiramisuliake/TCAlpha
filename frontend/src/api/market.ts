import { api } from "./client";

export interface Bar {
  symbol: string;
  dt: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number;
}

export async function getKline(symbol: string, period = "1d", limit = 200) {
  const r = await api.get("/market/kline", { params: { symbol, period, limit } });
  return r.data as { symbol: string; period: string; data: Bar[] };
}
