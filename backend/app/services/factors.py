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
        w = float(weights.get(fname, _DEFAULT_WEIGHTS.get(fname, 1.0)))
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
