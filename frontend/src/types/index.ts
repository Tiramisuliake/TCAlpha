export type Period = "1m" | "5m" | "15m" | "30m" | "1h" | "1d" | "1w" | "1M";

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
