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
  benchmark?: string; // 对比基准指数代码（默认 000300 沪深300）
  period?: string; // K 线周期：1d / 60m / 30m / 15m / 5m / 1m（默认 1d）
}

export interface EquityPoint {
  dt: string;
  value: number;
}

export interface MonthlyReturn {
  month: string; // YYYY-MM
  value: number;
}

/** 交易回合：一次进场 → 出场的完整周期（分批平仓拆成多个回合）。 */
export interface RoundTrip {
  entry_dt: string;
  exit_dt: string;
  holding_days: number;
  entry_price: number;
  exit_price: number;
  volume: number;
  pnl: number | null;
  return_pct: number | null;
  mae: number | null; // 持仓期间最大不利偏移（相对入场均价，负数）
  mfe: number | null; // 持仓期间最大有利偏移
  symbol?: string;    // 多标的回测（轮动/配对）时标记腿
  direction?: string; // long / short（配对含空头腿）
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
  // 基准对比（沪深300）：无基准数据时整组字段缺省
  benchmark?: string;
  benchmark_return?: number;
  excess_return?: number;
  alpha?: number;
  beta?: number;
  information_ratio?: number;
  benchmark_curve?: EquityPoint[];
  // 绩效深化（v0.8.x）：风险标量 + 收益分布 + 滚动/相对强弱
  calmar?: number;
  volatility?: number;
  avg_win?: number;
  avg_loss?: number;
  max_win_streak?: number;
  max_lose_streak?: number;
  max_dd_start?: string | null;
  max_dd_end?: string | null;
  max_dd_recovery?: string | null;
  max_dd_days?: number;
  monthly_returns?: MonthlyReturn[];
  rolling_sharpe?: EquityPoint[];
  rolling_beta?: EquityPoint[];
  relative_strength?: EquityPoint[];
  // 交易明细深化（v0.8.3）：回合 + 持仓周期 + MAE/MFE + 单笔期望
  round_trips?: RoundTrip[];
  avg_holding_days?: number;
  win_holding_days?: number;
  lose_holding_days?: number;
  avg_mae?: number | null;
  avg_mfe?: number | null;
  expectancy?: number;
  // 多标的动量轮动（v0.8.5）：仅 class_name=RotationBacktest 的结果携带
  rotation_symbols?: string[];
  rotation_holdings?: RotationHolding[];
  rotation_lookback?: number;
  rotation_rebalance_days?: number;
  // 配对交易（v0.8.6）：仅 class_name=PairTradingBacktest 的结果携带
  pair_symbols?: string[];
  pair_zscore?: EquityPoint[];
  pair_window?: number;
  pair_entry_z?: number;
  pair_exit_z?: number;
}

/** 轮动调仓记录：dt 调仓执行日，symbol 为空串表示空仓。 */
export interface RotationHolding {
  dt: string;
  symbol: string;
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
  period?: string; // K 线周期（默认 1d）
  oos_split?: number | null; // Walk-Forward 验证集占比（0.05~0.6，缺省不切分）
}

export interface SweepMetrics {
  total_return: number;
  annual_return: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  trade_count: number;
  // v0.8.5 寻优目标接入绩效深化指标（旧扫参结果缺省）
  calmar?: number;
  expectancy?: number;
}

export interface SweepResultRow {
  params: Record<string, number>;
  metrics: SweepMetrics;
  // Walk-Forward（v0.8.7）：样本外复测指标 + 衰减率（1 - 样本外/训练）
  oos_metrics?: SweepMetrics;
  decay?: number | null;
}

export interface SweepResult {
  target: string;
  param_keys: string[];
  count: number;
  results: SweepResultRow[];
  best: SweepResultRow | null;
  period?: string;
  oos_split?: number;
  train_bars?: number;
  test_bars?: number;
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
  // 短线技术选股字段（v0.8.9）
  vol_ratio?: number;
  ret5?: number;
  dist_high?: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
}

export interface ScreenResult {
  ready: boolean;
  count: number;
  candidates: ScreenCandidate[];
}

/** 短线技术选股请求（基于历史日 K 的量价形态）。 */
export interface ShortTermFilters {
  pattern: "volume_breakout" | "ma_long" | "pullback";
  breakout_window?: number;
  vol_window?: number;
  vol_ratio_min?: number;
  price_min?: number;
  price_max?: number;
  exclude_st?: boolean;
  limit?: number;
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

/** 模拟账户持仓单行（成本口径）。 */
export interface AccountPosition {
  symbol: string;
  volume: number;
  avg_price: number;
  cost: number;
}

/** 模拟资金账户快照：现金 + 持仓成本（不做实时市值）。 */
export interface AccountOut {
  balance: number;
  init_capital: number;
  position_cost: number;
  total_asset: number;
  positions: AccountPosition[];
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
