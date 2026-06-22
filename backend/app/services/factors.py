"""时序多因子选股引擎。

从 ArcticDB ``bar_1d`` 历史日 K 向量化计算一批**连续因子**（区别于 short_term 的布尔形态命中），
横截面 z-score 标准化后按方向加权综合打分排序。这是多因子选股的基座，后续可逐批扩充因子。

第一批因子（覆盖 动量 / 波动 / 趋势 / 量能 四类）：
  mom_20 / mom_60   多周期动量（区间收益率，越高越强）
  volatility        年化波动率（低波动溢价，越低越优）
  trend_slope       对数收盘价线性回归斜率年化（趋势强度，越高越强）
  vol_surge         近 5 日均量 / 近 20 日均量（量能放大，越高越强）

数据读取（list_symbols + read）为同步 IO，路由层用 ``asyncio.to_thread`` 包裹。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.short_term import _name_map

# 需要 mom_60（close[-61]）+ 余量
_MIN_BARS = 65

# 因子定义：name -> (中文名, higher_better 方向)
FACTORS: dict[str, tuple[str, bool]] = {
    "mom_20": ("20日动量", True),
    "mom_60": ("60日动量", True),
    "volatility": ("年化波动率", False),  # 低波动溢价
    "trend_slope": ("趋势斜率", True),
    "vol_surge": ("量能放大", True),
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

    # 量能放大：近 5 日均量 / 近 20 日均量
    vol_surge = 0.0
    if "volume" in df.columns:
        vol = pd.to_numeric(df["volume"], errors="coerce").dropna().to_numpy(dtype=float)
        if len(vol) >= 20:
            base = vol[-20:].mean()
            if base > 0:
                vol_surge = float(vol[-5:].mean() / base)

    return {
        "price": float(c[-1]),
        "mom_20": float(mom_20),
        "mom_60": float(mom_60),
        "volatility": volatility,
        "trend_slope": slope,
        "vol_surge": vol_surge,
    }


def _zscore(s: pd.Series) -> pd.Series:
    """横截面 z-score，clip 到 [-3,3] 抑制极值；恒定列给中性 0。"""
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-3.0, 3.0).fillna(0.0)


def factor_screen(filters: dict) -> dict:
    """多因子选股：截面 z-score 标准化 + 方向 + 加权综合分排序。

    filters：weights（{factor: w}，缺省 1.0）· price_min/max · exclude_st（默认 True）·
      limit（默认 50）· max_scan（默认 800）
    返回 {ready, count, candidates}（结构对齐 screener.screen）。
    """
    from app.db.arctic import get_library

    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return {"ready": False, "count": 0, "candidates": []}

    max_scan = int(filters.get("max_scan") or 800)
    symbols = symbols[:max_scan]
    names = _name_map(symbols)
    exclude_st = filters.get("exclude_st", True)
    price_min = filters.get("price_min")
    price_max = filters.get("price_max")

    rows: list[dict] = []
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        f = _compute_factors(df)
        if f is None:
            continue
        if price_min is not None and f["price"] < float(price_min):
            continue
        if price_max is not None and f["price"] > float(price_max):
            continue
        name = names.get(sym, "")
        if exclude_st and "ST" in name.upper():
            continue
        rows.append({"symbol": sym, "code": _to_code(sym), "name": name, **f})

    if not rows:
        return {"ready": True, "count": 0, "candidates": []}

    fdf = pd.DataFrame(rows)
    weights = filters.get("weights") or {}
    total = pd.Series(0.0, index=fdf.index)
    for fname, (_cn, higher) in FACTORS.items():
        w = float(weights.get(fname, 1.0))
        z = _zscore(fdf[fname])
        if not higher:
            z = -z
        fdf[f"{fname}_z"] = z.round(4)
        if w != 0:
            total = total + w * z
    fdf["score"] = total.round(4)
    fdf = fdf.sort_values("score", ascending=False)

    # 因子原始值 round，保证 JSON 紧凑
    for fname in FACTORS:
        fdf[fname] = pd.to_numeric(fdf[fname], errors="coerce").round(4)
    fdf["price"] = pd.to_numeric(fdf["price"], errors="coerce").round(2)

    limit = int(filters.get("limit") or 50)
    records = fdf.head(limit).to_dict("records")
    candidates = [
        {k: (None if pd.isna(v) else v) for k, v in rec.items()} for rec in records
    ]
    return {"ready": True, "count": len(candidates), "candidates": candidates}
