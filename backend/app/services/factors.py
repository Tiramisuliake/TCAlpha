"""时序多因子选股引擎。

从 ArcticDB ``bar_1d`` 历史日 K 向量化计算一批**连续因子**（区别于 short_term 的布尔形态命中），
横截面 z-score 标准化后按方向加权综合打分排序。这是多因子选股的基座，后续可逐批扩充因子。

第一批因子（追强风格，越高越优）：
  mom_20 / mom_60   多周期动量（区间收益率）
  volatility        年化波动率（低波动溢价，越低越优）
  trend_slope       对数收盘价线性回归斜率年化（趋势强度）
  vol_surge         近 5 日均量 / 近 20 日均量（量能放大）

第二批因子（反转 / 超卖风格，越低越优，与动量对冲）：
  rev_5             近 5 日收益（短期反转，跌多者优）
  rsi_14            RSI(14) Wilder 平滑（越低越超卖）
  boll_pctb         布林带 %B 位置（越接近下轨越超卖）

第三批因子（量价 / 资金行为，纯量价时序，缺省 0 按需开启）：
  corr_pv           近 20 日收盘价 vs 成交量相关性（量价齐升 > 0）
  amihud            Amihud 非流动性 mean(|日收益|/成交额)（越低流动性越好）
  obv_slope         能量潮 OBV 近 20 日回归斜率 / 日均量（资金净流入 > 0）

数据读取（list_symbols + read）为同步 IO，路由层用 ``asyncio.to_thread`` 包裹。
"""
from __future__ import annotations

import contextlib
import io

import numpy as np
import pandas as pd

from app.services.short_term import _name_map

# 需要 mom_60（close[-61]）+ 余量
_MIN_BARS = 65

# 因子快照缓存（最新截面因子原始值，与权重无关；每日收盘 beat 刷新）
_FACTOR_CACHE_KEY = "factor:snapshot:v1"
_FACTOR_CACHE_TTL = 60 * 60 * 24 + 3600  # 略超 1 天，留足到次日刷新

# 因子定义：name -> (中文名, higher_better 方向)
FACTORS: dict[str, tuple[str, bool]] = {
    "mom_20": ("20日动量", True),
    "mom_60": ("60日动量", True),
    "volatility": ("年化波动率", False),  # 低波动溢价
    "trend_slope": ("趋势斜率", True),
    "vol_surge": ("量能放大", True),
    # 反转 / 超卖风格（越低越优，与动量对冲）
    "rev_5": ("5日反转", False),
    "rsi_14": ("RSI超卖", False),
    "boll_pctb": ("布林%B", False),
    # 量价 / 资金行为（缺省 0，按需开启）
    "corr_pv": ("量价相关", True),
    "amihud": ("非流动性", False),  # 越低流动性越好
    "obv_slope": ("OBV斜率", True),
}

# 缺省权重：第一批动量/趋势/量能类等权 1，反转类 0（按需开启与动量对冲）。
# 与 FactorWeights schema 默认值一致——未显式指定的因子按此参与加权。
_DEFAULT_WEIGHTS: dict[str, float] = {
    "mom_20": 1.0, "mom_60": 1.0, "volatility": 1.0, "trend_slope": 1.0,
    "vol_surge": 1.0, "rev_5": 0.0, "rsi_14": 0.0, "boll_pctb": 0.0,
    "corr_pv": 0.0, "amihud": 0.0, "obv_slope": 0.0,
}


def _to_code(sym: str) -> str:
    return sym[2:] if sym[:2] in ("sh", "sz", "bj") else sym


def _compute_factors(df: pd.DataFrame) -> dict | None:
    """单只票的因子原始值；数据不足返回 None。"""
    if df is None or len(df) < _MIN_BARS or "close" not in df.columns:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < _MIN_BARS:
        return None
    c = close.to_numpy(dtype=float)

    mom_20 = c[-1] / c[-21] - 1.0
    mom_60 = c[-1] / c[-61] - 1.0

    # 年化波动率：近 60 日对数收益的样本标准差 * sqrt(252)
    rets = np.diff(np.log(c[-61:]))
    volatility = float(np.std(rets, ddof=1) * np.sqrt(252)) if len(rets) > 1 else 0.0

    # 趋势斜率：近 60 日对数收盘价对时间（日）的线性回归斜率，年化
    y = np.log(c[-60:])
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0]) * 252.0

    # 量、额序列（与 close 同长，A 股日 K 无停牌缺口假设）
    vol_arr = (
        pd.to_numeric(df["volume"], errors="coerce").to_numpy(dtype=float)
        if "volume" in df.columns else np.zeros(len(c))
    )
    amt_arr = (
        pd.to_numeric(df["amount"], errors="coerce").to_numpy(dtype=float)
        if "amount" in df.columns else np.zeros(len(c))
    )

    # 量能放大：近 5 日均量 / 近 20 日均量
    vol_surge = 0.0
    if len(vol_arr) >= 20:
        base = vol_arr[-20:].mean()
        if base > 0:
            vol_surge = float(vol_arr[-5:].mean() / base)

    # 短期反转：近 5 日收益（跌多者反转优）
    rev_5 = c[-1] / c[-6] - 1.0

    # RSI(14) Wilder 平滑（越低越超卖）
    delta = pd.Series(c).diff().fillna(0.0)
    avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    rsi_14 = 100.0 if avg_loss == 0 else float(100 - 100 / (1 + avg_gain / avg_loss))

    # 布林带 %B 位置（近 20 日，越接近下轨越超卖；可超出 [0,1]）
    recent = c[-20:]
    sd = recent.std(ddof=0)
    boll_pctb = float((c[-1] - (recent.mean() - 2 * sd)) / (4 * sd)) if sd > 0 else 0.5

    # 量价相关性：近 20 日收盘价 vs 成交量相关系数（量价齐升 > 0）
    corr_pv = 0.0
    if len(vol_arr) >= 20:
        c20, v20 = c[-20:], vol_arr[-20:]
        if np.std(c20) > 0 and np.std(v20) > 0:
            corr_pv = float(np.corrcoef(c20, v20)[0, 1])

    # Amihud 非流动性：近 20 日 mean(|日收益| / 成交额) ×1e8（越低越流动）
    amihud = 0.0
    if len(amt_arr) >= 21 and len(c) >= 21:
        ret20 = np.abs(np.diff(c[-21:]) / c[-21:-1])
        amt20 = amt_arr[-20:]
        mask = amt20 > 0
        if mask.any():
            amihud = float(np.mean(ret20[mask] / amt20[mask]) * 1e8)

    # OBV 斜率：能量潮近 20 日回归斜率 / 日均量（资金净流入 > 0）
    obv_slope = 0.0
    if len(vol_arr) >= 21 and len(c) >= 21:
        obv = np.cumsum(np.sign(np.diff(c)) * vol_arr[1:])
        obv20 = obv[-20:]
        base20 = vol_arr[-20:].mean()
        if base20 > 0:
            xx = np.arange(len(obv20), dtype=float)
            obv_slope = float(np.polyfit(xx, obv20, 1)[0] / base20)

    return {
        "price": float(c[-1]),
        "mom_20": float(mom_20),
        "mom_60": float(mom_60),
        "volatility": volatility,
        "trend_slope": slope,
        "vol_surge": vol_surge,
        "rev_5": float(rev_5),
        "rsi_14": rsi_14,
        "boll_pctb": boll_pctb,
        "corr_pv": corr_pv,
        "amihud": amihud,
        "obv_slope": obv_slope,
    }


def _zscore(s: pd.Series) -> pd.Series:
    """横截面 z-score，clip 到 [-3,3] 抑制极值；恒定列给中性 0。"""
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-3.0, 3.0).fillna(0.0)


def _compute_factor_frame(max_scan: int = 800) -> pd.DataFrame | None:
    """全市场最新截面因子原始值 DataFrame（symbol/code/name/price + 因子），**不过滤**。

    供 factor_screen 现算 fallback 与缓存刷新共用——价格/ST 过滤与加权在请求时做，
    缓存保持通用。无数据返回 None。
    """
    from app.db.arctic import get_library

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return None
    symbols = symbols[:max_scan]
    names = _name_map(symbols)

    rows: list[dict] = []
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        f = _compute_factors(df)
        if f is None:
            continue
        rows.append({"symbol": sym, "code": _to_code(sym), "name": names.get(sym, ""), **f})
    if not rows:
        return None

    fdf = pd.DataFrame(rows)
    for fname in FACTORS:
        fdf[fname] = pd.to_numeric(fdf[fname], errors="coerce").round(4)
    fdf["price"] = pd.to_numeric(fdf["price"], errors="coerce").round(2)
    return fdf


def refresh_factor_cache_sync(max_scan: int = 800) -> int:
    """算全市场因子快照写 Redis（beat 调用，同步 redis 客户端）。返回行数。"""
    import redis as sync_redis

    from app.config import settings
    from app.utils.trading_period import now_cn

    frame = _compute_factor_frame(max_scan)
    if frame is None or frame.empty:
        return 0
    payload = frame.to_json(orient="records", force_ascii=False)
    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(_FACTOR_CACHE_KEY, payload, ex=_FACTOR_CACHE_TTL)
        r.set(f"{_FACTOR_CACHE_KEY}:at", now_cn().strftime("%Y-%m-%d %H:%M"), ex=_FACTOR_CACHE_TTL)
    finally:
        r.close()
    return len(frame)


def _read_factor_cache() -> tuple[pd.DataFrame | None, str | None]:
    """读 Redis 因子快照缓存 → (DataFrame, 缓存时间)；缺失/异常返回 (None, None)。"""
    import redis as sync_redis

    from app.config import settings

    r = sync_redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    try:
        raw = r.get(_FACTOR_CACHE_KEY)
        at = r.get(f"{_FACTOR_CACHE_KEY}:at")
    except Exception:
        return None, None
    finally:
        with contextlib.suppress(Exception):
            r.close()
    if not raw:
        return None, None
    df = pd.read_json(io.StringIO(raw), dtype={"symbol": str, "code": str, "name": str})
    return df, at


def _trigger_factor_cache_refresh() -> None:
    """缓存未命中时触发后台刷新（下次命中）；无 broker 时静默忽略。"""
    try:
        from app.tasks.screen_tasks import refresh_factor_cache

        refresh_factor_cache.delay()
    except Exception:
        pass


def factor_screen(filters: dict) -> dict:
    """多因子选股：截面 z-score 标准化 + 方向 + 加权综合分排序。

    优先读 Redis 因子快照缓存（每日收盘 beat 刷新）——命中则跳过全市场 bar_1d 重算，
    仅做过滤 + 内存加权（大幅提速）；未命中现算并触发后台刷新。

    filters：weights · price_min/max · exclude_st（默认 True）· limit（默认 50）· max_scan（默认 800）
    返回 {ready, count, candidates, cached, as_of}（结构对齐 screener.screen）。
    """
    max_scan = int(filters.get("max_scan") or 800)
    fdf, as_of = _read_factor_cache()
    cached = fdf is not None and not fdf.empty
    if not cached:
        fdf = _compute_factor_frame(max_scan)
        _trigger_factor_cache_refresh()
    if fdf is None or fdf.empty:
        return {"ready": False, "count": 0, "candidates": [], "cached": False, "as_of": None}

    fdf = fdf.copy()
    price_min = filters.get("price_min")
    price_max = filters.get("price_max")
    if price_min is not None:
        fdf = fdf[fdf["price"] >= float(price_min)]
    if price_max is not None:
        fdf = fdf[fdf["price"] <= float(price_max)]
    if filters.get("exclude_st", True):
        fdf = fdf[~fdf["name"].astype(str).str.upper().str.contains("ST", na=False)]
    if fdf.empty:
        return {"ready": True, "count": 0, "candidates": [], "cached": cached, "as_of": as_of}

    weights = filters.get("weights") or {}
    total = pd.Series(0.0, index=fdf.index)
    for fname, (_cn, higher) in FACTORS.items():
        w = float(weights.get(fname, _DEFAULT_WEIGHTS.get(fname, 1.0)))
        z = _zscore(fdf[fname])
        if not higher:
            z = -z
        fdf[f"{fname}_z"] = z.round(4)
        if w != 0:
            total = total + w * z
    fdf["score"] = total.round(4)
    fdf = fdf.sort_values("score", ascending=False)

    limit = int(filters.get("limit") or 50)
    records = fdf.head(limit).to_dict("records")
    candidates = [
        {k: (None if pd.isna(v) else v) for k, v in rec.items()} for rec in records
    ]
    return {
        "ready": True, "count": len(candidates), "candidates": candidates,
        "cached": cached, "as_of": as_of,
    }


def _empty_ic(factor: str, hold_days: int) -> dict:
    return {
        "ready": False,
        "factor": factor,
        "hold_days": hold_days,
        "sample_count": 0,
        "mean_ic": 0.0,
        "ic_ir": 0.0,
        "ic_win_rate": 0.0,
        "long_short": 0.0,
        "quantiles": [],
    }


def factor_ic(
    factor: str,
    hold_days: int = 10,
    lookback: int = 240,
    sample_points: int = 8,
    max_scan: int = 300,
) -> dict:
    """单因子有效性检验：多采样时点横截面 rank IC + 5 档分层前瞻收益。

    对回看窗口内等间隔 sample_points 个时点，各算全市场横截面的：
      - rank IC：因子值 vs 未来 hold_days 收益的 Spearman 秩相关
      - 5 档分层：按因子值分位，记录各档未来收益（看单调性）
    汇总 IC 序列均值 / IC_IR（信息比率 = mean/std）/ 胜率（IC>0 占比），
    及分层平均收益与多空收益（long_short 按因子方向对齐，>0 表示因子有效）。

    采样时点用「距最新交易日的偏移」对齐（同市场交易日历），复用 ``_compute_factors``
    切片到历史截止点重算。数据读取为同步 IO，路由层用 ``asyncio.to_thread`` 包裹。
    """
    if factor not in FACTORS:
        raise ValueError(f"unknown factor: {factor} (allowed {list(FACTORS)})")

    from app.db.arctic import get_library

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return _empty_ic(factor, hold_days)

    symbols = symbols[:max_scan]
    frames: dict[str, pd.DataFrame] = {}
    closes: dict[str, np.ndarray] = {}
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or len(df) < _MIN_BARS + hold_days or "close" not in df.columns:
            continue
        frames[sym] = df
        closes[sym] = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    if not frames:
        return _empty_ic(factor, hold_days)

    offsets = sorted({int(round(o)) for o in np.linspace(hold_days, lookback, sample_points)})
    higher = FACTORS[factor][1]
    ic_list: list[float] = []
    quint_rets: dict[int, list[float]] = {q: [] for q in range(5)}

    for off in offsets:
        fvals: list[float] = []
        fwds: list[float] = []
        for sym, df in frames.items():
            c = closes[sym]
            n = len(c)
            t = n - 1 - off
            if t < _MIN_BARS - 1 or t + hold_days > n - 1:
                continue
            f = _compute_factors(df.iloc[: t + 1])
            if f is None or c[t] <= 0:
                continue
            fvals.append(f[factor])
            fwds.append(c[t + hold_days] / c[t] - 1.0)
        if len(fvals) < 5:
            continue
        sf, sr = pd.Series(fvals), pd.Series(fwds)
        # rank IC = 秩的 pearson 相关（等价 Spearman，避免 scipy）；因子/收益恒定时无定义，跳过
        if sf.nunique() > 1 and sr.nunique() > 1:
            ic = sf.rank().corr(sr.rank())
            if pd.notna(ic):
                ic_list.append(float(ic))
        try:
            q = pd.qcut(sf.rank(method="first"), 5, labels=False)
        except ValueError:
            continue
        for qi in range(5):
            rr = sr[q == qi]
            if len(rr):
                quint_rets[qi].append(float(rr.mean()))

    if not ic_list:
        return _empty_ic(factor, hold_days)

    mean_ic = float(np.mean(ic_list))
    std_ic = float(np.std(ic_list, ddof=0))
    ic_ir = mean_ic / std_ic if std_ic > 0 else 0.0
    win = sum(1 for x in ic_list if x > 0) / len(ic_list)
    quantiles = [
        {
            "q": qi + 1,
            "avg_return": round(float(np.mean(quint_rets[qi])), 6) if quint_rets[qi] else 0.0,
        }
        for qi in range(5)
    ]
    q1, q5 = quantiles[0]["avg_return"], quantiles[4]["avg_return"]
    long_short = (q5 - q1) if higher else (q1 - q5)

    return {
        "ready": True,
        "factor": factor,
        "hold_days": hold_days,
        "sample_count": len(ic_list),
        "mean_ic": round(mean_ic, 4),
        "ic_ir": round(ic_ir, 4),
        "ic_win_rate": round(win, 4),
        "long_short": round(long_short, 6),
        "quantiles": quantiles,
    }


def _summarize_ic(name: str, factor: str, ics: list[float], q1s: list[float], q5s: list[float], higher: bool) -> dict:
    """把一个因子的 IC 序列 + Q1/Q5 收益序列汇总为横评行。"""
    if not ics:
        return {
            "factor": factor, "name": name, "sample_count": 0,
            "mean_ic": 0.0, "ic_ir": 0.0, "ic_win_rate": 0.0, "long_short": 0.0,
        }
    mean_ic = float(np.mean(ics))
    std_ic = float(np.std(ics, ddof=0))
    q1 = float(np.mean(q1s)) if q1s else 0.0
    q5 = float(np.mean(q5s)) if q5s else 0.0
    return {
        "factor": factor,
        "name": name,
        "sample_count": len(ics),
        "mean_ic": round(mean_ic, 4),
        "ic_ir": round(mean_ic / std_ic, 4) if std_ic > 0 else 0.0,
        "ic_win_rate": round(sum(1 for x in ics if x > 0) / len(ics), 4),
        "long_short": round((q5 - q1) if higher else (q1 - q5), 6),
    }


def factor_ic_all(
    hold_days: int = 10,
    lookback: int = 240,
    sample_points: int = 8,
    max_scan: int = 300,
) -> list[dict]:
    """全因子 IC 横评：一次遍历数据，每采样时点切片一次算**所有**因子值，
    对每个因子算 rank IC + 多空收益，横向汇总对比（找最强因子）。

    比单因子 ``factor_ic`` 逐个调用省下重复读 IO / 重复切片——一个时点一次
    ``_compute_factors`` 即得全因子。返回每因子一行（含中文名），顺序对齐 FACTORS。
    空库 / 数据不足时每因子 sample_count=0。
    """
    from app.db.arctic import get_library

    names = list(FACTORS)
    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if symbols:
        symbols = symbols[:max_scan]
        frames: dict[str, pd.DataFrame] = {}
        closes: dict[str, np.ndarray] = {}
        for sym in symbols:
            try:
                df = lib.read(sym).data
            except Exception:
                continue
            if df is None or len(df) < _MIN_BARS + hold_days or "close" not in df.columns:
                continue
            frames[sym] = df
            closes[sym] = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    else:
        frames = {}

    ic_lists: dict[str, list[float]] = {f: [] for f in names}
    q1_lists: dict[str, list[float]] = {f: [] for f in names}
    q5_lists: dict[str, list[float]] = {f: [] for f in names}

    if frames:
        offsets = sorted({int(round(o)) for o in np.linspace(hold_days, lookback, sample_points)})
        for off in offsets:
            rows: list[tuple[dict, float]] = []
            for sym, df in frames.items():
                c = closes[sym]
                n = len(c)
                t = n - 1 - off
                if t < _MIN_BARS - 1 or t + hold_days > n - 1 or c[t] <= 0:
                    continue
                fdict = _compute_factors(df.iloc[: t + 1])
                if fdict is None:
                    continue
                rows.append((fdict, c[t + hold_days] / c[t] - 1.0))
            if len(rows) < 5:
                continue
            fwds = pd.Series([r[1] for r in rows])
            if fwds.nunique() <= 1:  # 收益恒定 → IC 无定义
                continue
            fwd_ranks = fwds.rank()
            for fname in names:
                fvals = pd.Series([r[0][fname] for r in rows])
                if fvals.nunique() > 1:  # 因子恒定时跳过（corr 无意义）
                    ic = fvals.rank().corr(fwd_ranks)
                    if pd.notna(ic):
                        ic_lists[fname].append(float(ic))
                try:
                    q = pd.qcut(fvals.rank(method="first"), 5, labels=False)
                except ValueError:
                    continue
                q1_lists[fname].append(float(fwds[q == 0].mean()))
                q5_lists[fname].append(float(fwds[q == 4].mean()))

    return [
        _summarize_ic(cn, fname, ic_lists[fname], q1_lists[fname], q5_lists[fname], higher)
        for fname, (cn, higher) in FACTORS.items()
    ]


def _weighted_score(fdf: pd.DataFrame, weights: dict) -> pd.Series:
    """截面 z-score 加权综合分（同 factor_screen 打分口径，供组合回测复用）。"""
    total = pd.Series(0.0, index=fdf.index)
    for fname, (_cn, higher) in FACTORS.items():
        w = float(weights.get(fname, _DEFAULT_WEIGHTS.get(fname, 1.0)))
        if w == 0:
            continue
        z = _zscore(fdf[fname])
        if not higher:
            z = -z
        total = total + w * z
    return total


def _portfolio_metrics(port_rets: list[float], bench_rets: list[float], rebalance_days: int) -> dict:
    """组合调仓收益序列 → 绩效指标（单次回测与参数寻优共用）。

    sharpe 按调仓收益序列年化；max_drawdown 含建仓起点 1.0；annual 按调仓周期数折年。
    """
    n_reb = len(port_rets)
    port_eq = np.cumprod([1.0 + r for r in port_rets])
    bench_eq = np.cumprod([1.0 + r for r in bench_rets])
    total_return = float(port_eq[-1] - 1.0)
    ppy = 252.0 / rebalance_days  # 每年调仓次数
    arr = np.asarray(port_rets)
    std = float(np.std(arr, ddof=0))
    sharpe = float(np.mean(arr) / std * np.sqrt(ppy)) if std > 0 else 0.0
    eq_full = np.concatenate([[1.0], port_eq])
    peak = np.maximum.accumulate(eq_full)
    mdd = float(((eq_full - peak) / peak).min())
    win = sum(1 for r in port_rets if r > 0) / n_reb
    annual = (1.0 + total_return) ** (ppy / n_reb) - 1.0 if total_return > -1 else -1.0
    excess = total_return - float(bench_eq[-1] - 1.0)
    return {
        "rebalance_count": n_reb,
        "total_return": round(total_return, 4),
        "annual_return": round(annual, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(mdd, 4),
        "win_rate": round(win, 4),
        "excess_return": round(excess, 4),
    }


def _load_portfolio_frames(max_scan: int, min_extra: int):
    """加载全市场日 K（过滤长度不足），返回 (frames, closes, ref_idx) 或 None。"""
    from app.db.arctic import get_library

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return None
    frames: dict[str, pd.DataFrame] = {}
    closes: dict[str, np.ndarray] = {}
    for sym in symbols[:max_scan]:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or len(df) < _MIN_BARS + min_extra or "close" not in df.columns:
            continue
        frames[sym] = df
        closes[sym] = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    if not frames:
        return None
    ref_idx = frames[max(frames, key=lambda s: len(frames[s]))].index
    return frames, closes, ref_idx


def _collect_portfolio_series(
    frames: dict[str, pd.DataFrame],
    closes: dict[str, np.ndarray],
    ref_idx,
    weights: dict,
    top_n: int,
    rebalance_days: int,
    lookback: int,
) -> tuple[list[float], list[float], list[str]]:
    """历史每调仓日按综合分选 top_n 等权，返回 (组合收益序列, 基准收益序列, 调仓日期)。"""
    ref_n = len(ref_idx)
    port_rets: list[float] = []
    bench_rets: list[float] = []
    dates: list[str] = []
    for off in range(lookback, 0, -rebalance_days):
        score_rows: dict[str, dict] = {}
        rets: dict[str, float] = {}
        for sym, df in frames.items():
            c = closes[sym]
            n = len(c)
            t = n - 1 - off
            if t < _MIN_BARS - 1 or t + rebalance_days > n - 1 or c[t] <= 0:
                continue
            fdict = _compute_factors(df.iloc[: t + 1])
            if fdict is None:
                continue
            score_rows[sym] = fdict
            rets[sym] = c[t + rebalance_days] / c[t] - 1.0
        if len(score_rows) < top_n:
            continue
        fdf = pd.DataFrame.from_dict(score_rows, orient="index")
        picks = _weighted_score(fdf, weights).sort_values(ascending=False).head(top_n).index
        port_rets.append(float(np.mean([rets[s] for s in picks])))
        bench_rets.append(float(np.mean(list(rets.values()))))
        ref_t = ref_n - 1 - off
        dates.append(str(ref_idx[ref_t].date()) if 0 <= ref_t < ref_n else f"T-{off}")
    return port_rets, bench_rets, dates


def factor_portfolio_backtest(
    weights: dict | None = None,
    top_n: int = 10,
    rebalance_days: int = 20,
    lookback: int = 480,
    max_scan: int = 300,
) -> dict:
    """多因子组合回测：历史每调仓日按综合分选 top_n 等权持有到下次调仓，
    拼组合净值并对比全市场等权基准。

    复用 ``_compute_factors`` 切片到调仓日重算 + z-score 加权打分（同 factor_screen）。
    调仓日按「距最新交易日偏移」对齐参考日历，净值为**调仓粒度**（非逐日）。
    指标：总收益 / 年化 / 夏普（调仓收益序列年化）/ 最大回撤 / 调仓胜率 / 对基准超额。
    """
    empty = {
        "ready": False, "rebalance_count": 0, "top_n": top_n,
        "total_return": 0.0, "annual_return": 0.0, "sharpe": 0.0,
        "max_drawdown": 0.0, "win_rate": 0.0, "excess_return": 0.0,
        "equity_curve": [], "benchmark_curve": [],
    }
    loaded = _load_portfolio_frames(max_scan, rebalance_days)
    if loaded is None:
        return empty
    frames, closes, ref_idx = loaded

    port_rets, bench_rets, dates = _collect_portfolio_series(
        frames, closes, ref_idx, weights or {}, top_n, rebalance_days, lookback
    )
    if not port_rets:
        return {**empty, "ready": True}

    port_eq = np.cumprod([1.0 + r for r in port_rets])
    bench_eq = np.cumprod([1.0 + r for r in bench_rets])
    equity_curve = [{"dt": dates[i], "value": round(float(port_eq[i]), 4)} for i in range(len(dates))]
    benchmark_curve = [{"dt": dates[i], "value": round(float(bench_eq[i]), 4)} for i in range(len(dates))]

    return {
        "ready": True,
        "top_n": top_n,
        **_portfolio_metrics(port_rets, bench_rets, rebalance_days),
        "equity_curve": equity_curve,
        "benchmark_curve": benchmark_curve,
    }


def factor_portfolio_walkforward(
    weights: dict | None = None,
    top_n: int = 10,
    rebalance_days: int = 20,
    lookback: int = 480,
    oos_ratio: float = 0.3,
    max_scan: int = 300,
) -> dict:
    """组合回测 walk-forward：调仓序列按时间切分样本内(IS)/样本外(OOS)两段，
    各算绩效对比——验证因子配置 / 寻优参数是否过拟合（OOS 是否保持 IS 表现）。

    复用 ``_collect_portfolio_series`` 得全调仓序列，前 (1-oos_ratio) 为 IS、后段为 OOS，
    各段净值独立从 1 起。调仓点不足以分段时 ready=True 但段为空。
    """
    empty = {
        "ready": False, "top_n": top_n, "rebalance_count": 0,
        "split_index": 0, "split_date": "",
        "in_sample": {}, "out_sample": {}, "in_curve": [], "out_curve": [],
    }
    loaded = _load_portfolio_frames(max_scan, rebalance_days)
    if loaded is None:
        return empty
    frames, closes, ref_idx = loaded

    port_rets, bench_rets, dates = _collect_portfolio_series(
        frames, closes, ref_idx, weights or {}, top_n, rebalance_days, lookback
    )
    n = len(port_rets)
    split = int(round(n * (1.0 - oos_ratio)))
    if n < 2 or split < 1 or n - split < 1:
        return {**empty, "ready": True, "rebalance_count": n}

    def _curve(rets: list[float], base_dates: list[str]) -> list[dict]:
        eq = np.cumprod([1.0 + r for r in rets])
        return [{"dt": base_dates[i], "value": round(float(eq[i]), 4)} for i in range(len(rets))]

    return {
        "ready": True,
        "top_n": top_n,
        "rebalance_count": n,
        "split_index": split,
        "split_date": dates[split],
        "in_sample": _portfolio_metrics(port_rets[:split], bench_rets[:split], rebalance_days),
        "out_sample": _portfolio_metrics(port_rets[split:], bench_rets[split:], rebalance_days),
        "in_curve": _curve(port_rets[:split], dates[:split]),
        "out_curve": _curve(port_rets[split:], dates[split:]),
    }


def factor_portfolio_sweep(
    weights: dict | None = None,
    top_n_list: list[int] | None = None,
    rebalance_list: list[int] | None = None,
    lookback: int = 480,
    max_scan: int = 300,
) -> list[dict]:
    """组合参数寻优：对 top_n × rebalance_days 网格各跑回测，返回每组合绩效。

    性能优化：同一 rebalance_days 下，先算每调仓日的综合分序列 + 区间收益（一次），
    不同 top_n 只是 ``head(top_n)`` 选股不同，共享因子计算，避免 N×M 次完整重算。
    """
    from app.db.arctic import get_library

    top_ns = sorted({int(x) for x in (top_n_list or [10, 20, 30]) if x >= 1})
    rebals = sorted({int(x) for x in (rebalance_list or [10, 20, 40]) if x >= 1})
    if not top_ns or not rebals:
        return []

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return []
    symbols = symbols[:max_scan]

    min_need = _MIN_BARS + max(rebals)
    frames: dict[str, pd.DataFrame] = {}
    closes: dict[str, np.ndarray] = {}
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or len(df) < min_need or "close" not in df.columns:
            continue
        frames[sym] = df
        closes[sym] = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    if not frames:
        return []

    weights = weights or {}
    results: list[dict] = []
    for rebal in rebals:
        # 每调仓日的 (综合分 series, 区间收益 dict)——多 top_n 共享
        per: list[tuple[pd.Series, dict]] = []
        for off in range(lookback, 0, -rebal):
            score_rows: dict[str, dict] = {}
            rets: dict[str, float] = {}
            for sym, df in frames.items():
                c = closes[sym]
                n = len(c)
                t = n - 1 - off
                if t < _MIN_BARS - 1 or t + rebal > n - 1 or c[t] <= 0:
                    continue
                fdict = _compute_factors(df.iloc[: t + 1])
                if fdict is None:
                    continue
                score_rows[sym] = fdict
                rets[sym] = c[t + rebal] / c[t] - 1.0
            if not score_rows:
                continue
            fdf = pd.DataFrame.from_dict(score_rows, orient="index")
            per.append((_weighted_score(fdf, weights), rets))

        for top_n in top_ns:
            port_rets: list[float] = []
            bench_rets: list[float] = []
            for total, rets in per:
                if len(total) < top_n:
                    continue
                picks = total.sort_values(ascending=False).head(top_n).index
                port_rets.append(float(np.mean([rets[s] for s in picks])))
                bench_rets.append(float(np.mean(list(rets.values()))))
            if not port_rets:
                continue
            results.append({
                "top_n": top_n,
                "rebalance_days": rebal,
                **_portfolio_metrics(port_rets, bench_rets, rebal),
            })
    return results
