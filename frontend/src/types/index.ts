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

// ── Strategy ──────────────────────────────────────────────

export interface StrategyConfig {
  id: number;
  name: string;
  class_name: string;
  symbol: string;
  params: Record<string, unknown>;
  state: Record<string, unknown>;
  status: "stopped" | "running" | "error";
  created_at: string;
  updated_at: string;
}

export interface StrategyCreate {
  name: string;
  class_name: string;
  symbol: string;
  params: Record<string, unknown>;
}

export interface StrategyClassInfo {
  class_name: string;
  author: string;
  params_schema: Record<string, { title: string; default: unknown; type: string }>;
}

// ── Backtest ──────────────────────────────────────────────

export interface BacktestSubmit {
  name: string;
  class_name: string;
  symbol: string;
  params: Record<string, unknown>;
  start_date: string;
  end_date: string;
  init_capital: number;
  commission_rate: number;
  slippage: number;
}

export interface EquityPoint {
  dt: string;
  value: number;
}

export interface BacktestResult {
  total_return: number;
  annual_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  trade_count: number;
  win_rate: number;
  profit_factor: number;
  init_capital: number;
  final_equity: number;
  equity_curve: EquityPoint[];
}

export interface BacktestStatus {
  job_id: number;
  status: "pending" | "running" | "done" | "failed";
  result: BacktestResult | null;
  error: string | null;
}

export interface BacktestTrade {
  id: number;
  job_id: number;
  symbol: string;
  direction: string;
  offset: string;
  price: number;
  volume: number;
  dt: string;
  pnl: number | null;
}
