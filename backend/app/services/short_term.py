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
_PATTERN_CN = {
    "volume_breakout": "放量突破",
    "ma_long": "均线多头",
    "pullback": "回踩企稳",
    "limit_up": "涨停打板",
}
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


# ── 涨停次日溢价统计（打板复盘，v0.8.12）────────────────────────────────


def _limit_up_samples(df: pd.DataFrame, symbol: str, lookback: int) -> list[dict]:
    """扫单只日 K 的历史涨停日，记录每个涨停日「次日」的开盘/收盘/最高溢价 + 当时连板数。

    溢价基准为涨停日收盘价；涨停判定同 _count_boards（按板块涨停价）。
    只取最近 lookback 个交易日内、且有次日数据的涨停日。
    """
    n = len(df)
    if n < 2 or not {"open", "high", "close"} <= set(df.columns):
        return []
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    prev = close.shift(1)
    limit_price = (prev * (1 + _board_limit_pct(symbol))).round(2)
    is_lu = (close >= (limit_price - 0.001)).tolist()

    boards_arr = [0] * n
    run = 0
    for i in range(n):
        run = run + 1 if is_lu[i] else 0
        boards_arr[i] = run

    start = max(1, n - lookback)
    out: list[dict] = []
    for i in range(start, n - 1):  # 需要 i+1 次日
        if not is_lu[i]:
            continue
        c0 = float(close.iloc[i])
        if c0 <= 0:
            continue
        out.append({
            "open_prem": float(open_.iloc[i + 1]) / c0 - 1,
            "close_prem": float(close.iloc[i + 1]) / c0 - 1,
            "high_prem": float(high.iloc[i + 1]) / c0 - 1,
            "boards": boards_arr[i],
            "next_limit_up": bool(is_lu[i + 1]),  # 次日续板 = 晋级 N+1
        })
    return out


def _board_group(boards: int) -> str:
    if boards <= 1:
        return "1板"
    if boards == 2:
        return "2板"
    return "3板+"


def limit_up_premium(symbol: str | None = None, lookback: int = 250, max_scan: int = 800) -> dict:
    """涨停次日溢价统计（打板复盘）。

    单 symbol（传 symbol）或全市场（默认，扫 ArcticDB 已下载票）。汇总：样本数、
    次日平均开盘/收盘/最高溢价、次日红盘率（收盘 > 涨停日收盘占比），并按连板高度分组。
    """
    from app.db.arctic import get_library
    from app.utils.symbol import normalize

    lib = get_library("bar_1d")
    all_syms = lib.list_symbols()
    if not all_syms:
        return {"ready": False, "count": 0}

    if symbol:
        key = normalize(symbol)
        syms = [key] if key in all_syms else []
    else:
        syms = all_syms[:max_scan]

    samples: list[dict] = []
    for sym in syms:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or df.empty:
            continue
        samples.extend(_limit_up_samples(df, sym, lookback))

    return _aggregate_premium(samples)


def _aggregate_premium(samples: list[dict]) -> dict:
    if not samples:
        return {
            "ready": True, "count": 0,
            "avg_open_premium": 0.0, "avg_close_premium": 0.0,
            "avg_high_premium": 0.0, "next_day_win_rate": 0.0, "by_boards": [],
        }

    op = np.array([s["open_prem"] for s in samples])
    cl = np.array([s["close_prem"] for s in samples])
    hi = np.array([s["high_prem"] for s in samples])

    groups: list[dict] = []
    for label in ("1板", "2板", "3板+"):
        sub = [s for s in samples if _board_group(s["boards"]) == label]
        if not sub:
            continue
        sub_cl = np.array([s["close_prem"] for s in sub])
        promote = np.array([1.0 if s["next_limit_up"] else 0.0 for s in sub])
        groups.append({
            "boards": label,
            "count": len(sub),
            "avg_open": round(float(np.mean([s["open_prem"] for s in sub])), 4),
            "avg_close": round(float(sub_cl.mean()), 4),
            "win_rate": round(float((sub_cl > 0).mean()), 4),
            "promote_rate": round(float(promote.mean()), 4),  # 次日续板率（晋级 N+1）
        })

    return {
        "ready": True,
        "count": len(samples),
        "avg_open_premium": round(float(op.mean()), 4),
        "avg_close_premium": round(float(cl.mean()), 4),
        "avg_high_premium": round(float(hi.mean()), 4),
        "next_day_win_rate": round(float((cl > 0).mean()), 4),
        "by_boards": groups,
    }


# ── 单票形态匹配（盯盘标记，v0.8.17）─────────────────────────────────────


def match_patterns(
    symbols: list[str],
    breakout_window: int = 20,
    vol_window: int = 5,
    vol_ratio_min: float = 1.5,
    min_boards: int = 1,
) -> dict[str, list[str]]:
    """对给定 symbols 各算当前命中的短线形态（中文名列表），供盯盘页实时标记。

    复用 _tech_snapshot + _match；不在 ArcticDB / 数据不足 / 非法代码均返回空列表。
    """
    from app.db.arctic import get_library
    from app.utils.symbol import normalize

    lib = get_library("bar_1d")
    avail = set(lib.list_symbols())
    out: dict[str, list[str]] = {}
    for sym in symbols:
        names: list[str] = []
        try:
            key = normalize(sym)
        except ValueError:
            out[sym] = names
            continue
        if key in avail:
            try:
                df = lib.read(key).data
                snap = _tech_snapshot(df, breakout_window, vol_window, symbol=key)
                if snap is not None:
                    names = [
                        _PATTERN_CN[p]
                        for p in PATTERNS
                        if _match(p, snap, vol_ratio_min, min_boards)
                    ]
            except Exception:
                names = []
        out[sym] = names
    return out


# ── 形态前瞻收益统计（形态有效性验证，v0.8.18）──────────────────────────


def _boards_series(is_lu: pd.Series) -> pd.Series:
    """连板计数序列：连续涨停累加，遇非涨停归零（pandas streak 计数）。"""
    grp = (~is_lu).cumsum()
    return is_lu.groupby(grp).cumsum().astype(int)


def _pattern_hit_series(
    df: pd.DataFrame,
    pattern: str,
    symbol: str,
    breakout_window: int,
    vol_window: int,
    vol_ratio_min: float,
    min_boards: int,
) -> pd.Series:
    """向量化逐日形态命中布尔序列（与 _match 同口径）。"""
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    if pattern == "volume_breakout":
        prev_high = high.rolling(breakout_window).max().shift(1)
        vol_base = vol.rolling(vol_window).mean().shift(1)
        hit = (close >= prev_high) & (vol >= vol_ratio_min * vol_base)
    elif pattern == "ma_long":
        ma5, ma10, ma20 = (close.rolling(w).mean() for w in (5, 10, 20))
        hit = (ma5 > ma10) & (ma10 > ma20) & (close >= ma5)
    elif pattern == "pullback":
        ma10, ma20 = close.rolling(10).mean(), close.rolling(20).mean()
        hit = (close > ma20) & (low <= ma10) & (ma10 <= close)
    elif pattern == "limit_up":
        prev = close.shift(1)
        limit_price = (prev * (1 + _board_limit_pct(symbol))).round(2)
        is_lu = close >= (limit_price - 0.001)
        hit = _boards_series(is_lu) >= min_boards
    else:
        raise ValueError(f"unknown pattern: {pattern}")
    return hit.fillna(False).astype(bool)


def pattern_forward_stats(
    pattern: str,
    symbol: str | None = None,
    hold_days: int = 5,
    lookback: int = 500,
    max_scan: int = 300,
    breakout_window: int = 20,
    vol_window: int = 5,
    vol_ratio_min: float = 1.5,
    min_boards: int = 1,
) -> dict:
    """形态前瞻收益统计：历史每次形态命中后，持有 hold_days 日的收益分布。

    单 symbol（传 symbol）或全市场（默认，扫已下载票）。回答「该形态命中后
    N 日平均赚多少、胜率多少」，验证形态有效性。
    """
    if pattern not in PATTERNS:
        raise ValueError(f"unknown pattern: {pattern} (allowed {PATTERNS})")

    from app.db.arctic import get_library
    from app.utils.symbol import normalize

    lib = get_library("bar_1d")
    avail = lib.list_symbols()
    if not avail:
        return {"ready": False, "pattern": pattern, "hold_days": hold_days, "count": 0}

    if symbol:
        key = normalize(symbol)
        syms = [key] if key in avail else []
    else:
        syms = avail[:max_scan]

    rets: list[float] = []
    for sym in syms:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        n = len(df)
        if df is None or n < _MIN_BARS + hold_days or "close" not in df.columns:
            continue
        hit = _pattern_hit_series(
            df, pattern, sym, breakout_window, vol_window, vol_ratio_min, min_boards
        )
        close = df["close"]
        fwd = close.shift(-hold_days) / close - 1
        valid = (hit & fwd.notna()).to_numpy()
        if n > lookback:
            valid[: n - lookback] = False  # 只统计最近 lookback 根
        rets.extend(fwd.to_numpy()[valid].tolist())

    return _agg_forward(rets, pattern, hold_days)


def _agg_forward(rets: list[float], pattern: str, hold_days: int) -> dict:
    base = {"ready": True, "pattern": pattern, "hold_days": hold_days, "count": len(rets)}
    if not rets:
        return {**base, "avg_return": 0.0, "win_rate": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "median_return": 0.0}
    a = np.array(rets, dtype=float)
    wins, losses = a[a > 0], a[a < 0]
    return {
        **base,
        "avg_return": round(float(a.mean()), 4),
        "win_rate": round(float((a > 0).mean()), 4),
        "avg_win": round(float(wins.mean()), 4) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else 0.0,
        "median_return": round(float(np.median(a)), 4),
    }
