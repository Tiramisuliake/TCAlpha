"""短线技术选股：读 ArcticDB 历史日 K，按短线买点形态扫描候选股。

与 ``screener.py`` 的截面快照选股互补 —— 后者基于当日市值/PE/换手，前者
基于历史量价形态（均线、突破、量比），面向短线交易的技术买点。

形态（pattern）：
  - volume_breakout：放量突破前 N 日新高（启动信号）
  - ma_long：均线多头排列 MA5>MA10>MA20 且收盘站上 MA5（强势趋势）
  - pullback：上升趋势中回踩 MA10 企稳（短线低吸点）

扫描对象为 ArcticDB ``bar_1d`` 已下载历史的股票；命中形态后按「短线动能」
（量比 + 近 5 日涨幅 + 距新高接近度）组内归一化打分排序。纯 pandas 计算，
不依赖 vnpy，便于测试与提速。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

PATTERNS = ("volume_breakout", "ma_long", "pullback", "limit_up")
_MIN_BARS = 30  # 算 MA20 + 突破窗口所需最少 bar 数


def _board_limit_pct(symbol: str) -> float:
    """A 股板块涨跌停比例：创业板(300/301)/科创板(688) 20%，北交所 30%，主板 10%。

    ST 需股票名判定，扫描层已可 exclude_st；此处按板块比例（不单列 5%）。
    """
    s = symbol.lower()
    raw = s[2:] if s[:2] in ("sh", "sz", "bj") else s
    if s.startswith("bj") or raw.startswith(("8", "4")):
        return 0.30
    if raw.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def _name_map(symbols: list[str]) -> dict[str, str]:
    """从 PG symbols 表批量取 symbol→name（同步 session，选股扫描在 service 内跑）。"""
    from sqlalchemy import select

    from app.db.models.symbol import Symbol
    from app.db.postgres import SyncSessionLocal

    if not symbols:
        return {}
    try:
        with SyncSessionLocal() as db:
            rows = db.execute(
                select(Symbol.symbol, Symbol.name).where(Symbol.symbol.in_(symbols))
            ).all()
        return {s: n for s, n in rows}
    except Exception as exc:
        logger.warning("short_term name map failed: {}", exc)
        return {}


def _count_boards(close: pd.Series, limit_pct: float) -> int:
    """从最后一根往前数连续涨停天数（价格判定：收盘 ≥ 昨收涨停价）。"""
    prev = close.shift(1)
    limit_price = (prev * (1 + limit_pct)).round(2)
    is_lu = close >= (limit_price - 0.001)
    boards = 0
    for ok in reversed(is_lu.tolist()):
        if ok is True:
            boards += 1
        else:
            break
    return boards


def _tech_snapshot(
    df: pd.DataFrame, breakout_window: int, vol_window: int, symbol: str = ""
) -> dict | None:
    """从单只日 K 算短线技术快照；数据不足返回 None。"""
    if len(df) < max(_MIN_BARS, breakout_window + 1, vol_window + 1):
        return None
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    last_close = float(close.iloc[-1])
    last_low = float(low.iloc[-1])
    if last_close <= 0:
        return None

    ma5 = float(close.iloc[-5:].mean())
    ma10 = float(close.iloc[-10:].mean())
    ma20 = float(close.iloc[-20:].mean())

    # 量比：今日量 / 前 vol_window 日均量（不含今日）
    vol_base = float(vol.iloc[-vol_window - 1 : -1].mean())
    vol_ratio = float(vol.iloc[-1]) / vol_base if vol_base > 0 else 0.0

    # 前 N 日最高（不含今日）→ 突破基准
    prev_high = float(high.iloc[-breakout_window - 1 : -1].max())
    # 近 breakout_window 日（含今日）区间最高 → 距新高
    range_high = float(high.iloc[-breakout_window:].max())
    dist_high = last_close / range_high - 1 if range_high > 0 else -1.0  # ≤0，越接近 0 越靠新高

    ret5 = last_close / float(close.iloc[-6]) - 1 if float(close.iloc[-6]) > 0 else 0.0

    boards = _count_boards(close, _board_limit_pct(symbol)) if symbol else 0

    return {
        "close": round(last_close, 3),
        "ma5": round(ma5, 3),
        "ma10": round(ma10, 3),
        "ma20": round(ma20, 3),
        "vol_ratio": round(vol_ratio, 2),
        "prev_high": round(prev_high, 3),
        "dist_high": round(dist_high, 4),
        "ret5": round(ret5, 4),
        "low": last_low,
        "boards": boards,
    }


def _match(pattern: str, s: dict, vol_ratio_min: float, min_boards: int = 1) -> bool:
    """形态判定：传入技术快照，返回是否命中。"""
    if pattern == "volume_breakout":
        # 收盘突破前 N 日最高 + 放量确认
        return s["close"] >= s["prev_high"] and s["vol_ratio"] >= vol_ratio_min
    if pattern == "ma_long":
        # 均线多头排列且收盘站上 MA5
        return s["ma5"] > s["ma10"] > s["ma20"] and s["close"] >= s["ma5"]
    if pattern == "pullback":
        # 上升趋势（收盘在 MA20 上方）+ 当日回踩 MA10 并收回其上（企稳）
        return s["close"] > s["ma20"] and s["low"] <= s["ma10"] <= s["close"]
    if pattern == "limit_up":
        # 涨停打板：当前连板数 ≥ 下限（min_boards=1 即今日涨停）
        return s.get("boards", 0) >= min_boards
    return False


def scan_short_term(filters: dict) -> dict:
    """遍历 ArcticDB bar_1d 已有 symbol，按短线形态筛选并打分排序。

    filters：pattern（默认 volume_breakout）· breakout_window（默认 20）·
      vol_window（默认 5）· vol_ratio_min（默认 1.5）· price_min/max ·
      exclude_st（默认 True）· limit（默认 50）· max_scan（默认 800，扫描上限保护）
    返回 {ready, count, candidates}（结构对齐 screener.screen）。
    """
    from app.db.arctic import get_library

    pattern = filters.get("pattern") or "volume_breakout"
    if pattern not in PATTERNS:
        raise ValueError(f"unknown pattern: {pattern} (allowed {PATTERNS})")

    breakout_window = int(filters.get("breakout_window") or 20)
    vol_window = int(filters.get("vol_window") or 5)
    vol_ratio_min = float(filters.get("vol_ratio_min") or 1.5)
    min_boards = int(filters.get("min_boards") or 1)
    price_min = filters.get("price_min")
    price_max = filters.get("price_max")
    exclude_st = filters.get("exclude_st", True)
    limit = int(filters.get("limit") or 50)
    max_scan = int(filters.get("max_scan") or 800)

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        # 无历史 K 线：提示前端先下载数据
        return {"ready": False, "count": 0, "candidates": []}
    symbols = symbols[:max_scan]
    names = _name_map(symbols)

    hits: list[dict] = []
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        snap = _tech_snapshot(df, breakout_window, vol_window, symbol=sym)
        if snap is None:
            continue
        if price_min is not None and snap["close"] < float(price_min):
            continue
        if price_max is not None and snap["close"] > float(price_max):
            continue
        name = names.get(sym, "")
        if exclude_st and "ST" in name.upper():
            continue
        if not _match(pattern, snap, vol_ratio_min, min_boards):
            continue
        hits.append({
            "symbol": sym,
            "code": sym[2:] if sym[:2] in ("sh", "sz", "bj") else sym,
            "name": name,
            "price": snap["close"],
            "vol_ratio": snap["vol_ratio"],
            "ret5": snap["ret5"],
            "dist_high": snap["dist_high"],
            "ma5": snap["ma5"],
            "ma10": snap["ma10"],
            "ma20": snap["ma20"],
            "boards": snap["boards"],
        })

    candidates = _score(hits, pattern)[:limit]
    return {"ready": True, "count": len(candidates), "candidates": candidates}


def _score(hits: list[dict], pattern: str = "volume_breakout") -> list[dict]:
    """打分排序。

    通用形态：短线动能（量比↑ + 近5日涨幅↑ + 距新高接近度↑）组内 min-max 归一等权。
    涨停打板（limit_up）：连板高度优先（boards），同板数再看量比 —— 打板看高度。
    """
    if not hits:
        return []

    def _norm(key: str, ascending: bool) -> list[float]:
        vals = np.array([h[key] for h in hits], dtype=float)
        lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
            return [0.0] * len(hits)
        n = (vals - lo) / (hi - lo)
        return list(n if ascending else 1 - n)

    if pattern == "limit_up":
        for h in hits:
            h["score"] = float(h.get("boards", 0))
        return sorted(hits, key=lambda h: (h["boards"], h["vol_ratio"]), reverse=True)

    s_vol = _norm("vol_ratio", ascending=True)
    s_ret = _norm("ret5", ascending=True)
    s_high = _norm("dist_high", ascending=True)  # dist_high ≤0，越大(越接近0)越靠新高
    for h, a, b, c in zip(hits, s_vol, s_ret, s_high, strict=False):
        h["score"] = round(a + b + c, 4)
    return sorted(hits, key=lambda h: h["score"], reverse=True)
