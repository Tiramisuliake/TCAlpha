import { api } from "./client";

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
