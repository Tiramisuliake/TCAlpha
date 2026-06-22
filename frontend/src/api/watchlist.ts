import axios from "axios";
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

export interface BatchWatchResult {
  added: string[];
  skipped: string[]; // 已在自选（后端 409）
  failed: string[]; // 其他错误
}

/** 批量加自选：并发逐个调 addWatch，复用后端唯一约束（409=已存在）做去重统计。 */
export const addWatchBatch = async (
  symbols: string[],
  notes = "",
): Promise<BatchWatchResult> => {
  const results = await Promise.allSettled(symbols.map((s) => addWatch(s, notes)));
  const added: string[] = [];
  const skipped: string[] = [];
  const failed: string[] = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") {
      added.push(symbols[i]);
    } else if (axios.isAxiosError(r.reason) && r.reason.response?.status === 409) {
      skipped.push(symbols[i]);
    } else {
      failed.push(symbols[i]);
    }
  });
  return { added, skipped, failed };
};

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
