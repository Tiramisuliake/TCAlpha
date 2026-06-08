import { api } from "./client";
import type { AiAlert } from "./ai_alerts";

export interface WatchlistItem {
  id: number;
  user_id: number;
  symbol: string;
  notes: string;
  added_at: string;
}

export const listWatchlist = () =>
  api.get<WatchlistItem[]>("/watchlist").then((r) => r.data);

export const addWatch = (symbol: string, notes = "") =>
  api.post<WatchlistItem>("/watchlist", { symbol, notes }).then((r) => r.data);

export const deleteWatch = (id: number) =>
  api.delete(`/watchlist/${id}`).then((r) => r.data);

// ── 盯盘驾驶舱 ──────────────────────────────────────────────

export interface BoardItem {
  symbol: string;
  notes: string;
  name: string | null;
  price: number | null;
  pct_chg: number | null;
  amount: number | null;
}

export interface BoardOut {
  items: BoardItem[];
  alerts: AiAlert[];
  quote_ready: boolean;
}

export const getBoard = () =>
  api.get<BoardOut>("/watchlist/board").then((r) => r.data);
