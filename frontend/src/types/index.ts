export type Period = "1m" | "5m" | "15m" | "30m" | "60m" | "1d";

export interface Symbol {
  id: number;
  symbol: string;
  code: string;
  exchange: string;
  name: string;
  industry: string | null;
  list_date: string | null;
  is_active: boolean;
}

export interface SymbolListResponse {
  items: Symbol[];
  total: number;
}

export interface KlineBar {
  dt: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number | null;
}

export interface KlineResponse {
  symbol: string;
  period: string;
  bars: KlineBar[];
  total: number;
}

export interface StrategyConfig {
  id: number;
  name: string;
  className: string;
  symbol: string;
  params: Record<string, unknown>;
  state: Record<string, unknown>;
  status: "stopped" | "running" | "error";
  createdAt: string;
  updatedAt: string;
}
