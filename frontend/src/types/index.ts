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

// ── Real-time Quote (Phase 5 C) ──────────────────────────────

export interface QuoteUpdate {
  symbol: string;
  code: string;
  name?: string;
  price: number;
  change?: number;
  pct_chg?: number;
  volume?: number;
  amount?: number;
  open?: number;
  high?: number;
  low?: number;
  pre_close?: number;
  ts: string;
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
  params_schema: Record<
    string,
    { title: string; default: unknown; type: string; minimum?: number | null; maximum?: number | null }
  >;
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

export interface SweepSubmit {
  name: string;
  class_name: string;
  symbol: string;
  param_grid: Record<string, number[]>;
  target: string;
  start_date: string;
  end_date: string;
  init_capital: number;
  commission_rate: number;
  slippage: number;
}

export interface SweepResultRow {
  params: Record<string, number>;
  metrics: {
    total_return: number;
    annual_return: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    trade_count: number;
  };
}

export interface SweepResult {
  target: string;
  param_keys: string[];
  count: number;
  results: SweepResultRow[];
  best: SweepResultRow | null;
}

export interface SweepStatus {
  job_id: number;
  status: "pending" | "running" | "done" | "failed";
  result: SweepResult | null;
  error: string | null;
}

// ── Screener 选股器 ───────────────────────────────────────

export interface ScreenFilters {
  market_cap_min?: number;
  market_cap_max?: number;
  pe_min?: number;
  pe_max?: number;
  amount_min?: number;
  turnover_min?: number;
  pct_chg_min?: number;
  pct_chg_max?: number;
  exclude_st?: boolean;
  sort_by?: string;
  limit?: number;
  factor_mode?: boolean;
  w_momentum?: number;
  w_value?: number;
  w_turnover?: number;
}

export interface ScreenCandidate {
  symbol: string;
  code: string;
  name: string;
  price?: number;
  pct_chg?: number;
  amount?: number;
  turnover?: number;
  market_cap?: number;
  pe?: number;
  pb?: number;
  score?: number;
}

export interface ScreenResult {
  ready: boolean;
  count: number;
  candidates: ScreenCandidate[];
}

// ── Sim Trading ───────────────────────────────────────────

export interface SimOrder {
  id: number;
  strategy_id: number | null;
  symbol: string;
  direction: string;
  offset: string;
  price: number;
  volume: number;
  filled_volume: number;
  status: "submitted" | "partial" | "filled" | "cancelled" | "rejected";
  created_at: string;
  updated_at: string;
}

export interface PositionSummary {
  symbol: string;
  net_position: number;
}

export interface PlaceOrderRequest {
  symbol: string;
  direction: "long" | "short";
  offset: "open" | "close";
  volume: number;
}

export interface StrategySignal {
  strategy_id: number;
  symbol: string;
  bar_dt: string;
  direction: number;
  strength: number;
  tip: string;
  pos: number;
  ts: string;
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

// ── Auth (Phase 7 v0.7.0b) ────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: number;
}

export type DataScope = "self" | "dept" | "all";

export interface MeResponse {
  id: number;
  username: string;
  display_name: string;
  is_super: boolean;
  roles: string[];
  permissions: string[];
  data_scope: DataScope;
  last_login_at: string | null;
}

// ── System Management (Phase 7 v0.7.2) ────────────────────

export interface PermissionOut {
  id: number;
  code: string;
  name: string;
  category: string;
  description: string;
}

export interface RoleOut {
  id: number;
  code: string;
  name: string;
  data_scope: DataScope;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface RoleDetailOut extends RoleOut {
  permission_codes: string[];
}

export interface RoleCreate {
  code: string;
  name: string;
  data_scope?: DataScope;
  description?: string;
}

export interface RoleUpdate {
  name?: string;
  data_scope?: DataScope;
  description?: string;
}

export interface UserListItem {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  is_super: boolean;
  created_at: string;
  last_login_at: string | null;
  role_codes: string[];
}

export interface UserCreate {
  username: string;
  password: string;
  display_name?: string;
  email?: string | null;
  is_active?: boolean;
  is_super?: boolean;
  role_codes: string[];
}

export interface UserUpdate {
  display_name?: string;
  email?: string | null;
  is_active?: boolean;
}
