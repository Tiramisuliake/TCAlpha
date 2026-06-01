"""实时报价服务（Phase 5 C 阶段）。

通过 AKShare 全市场快照 ``stock_zh_a_spot_em`` 拉取批量报价，按 symbol 推送到
Redis pub/sub。前端 ``/ws/quote?symbol=xxx`` 订阅对应 channel。

⚠️ 不在 endpoint 里直调，必须走 Celery（``app.tasks.data_tasks.push_quotes``）。
"""
from __future__ import annotations

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.data import wait_for_rate_limit
from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
from app.utils.akshare_compat import _get_eastmoney_session
from app.utils.symbol import code, normalize
from app.utils.trading_period import now_cn

_QUOTE_COLS = {
    "代码": "code",
    "名称": "name",
    "最新价": "price",
    "涨跌额": "change",
    "涨跌幅": "pct_chg",
    "成交量": "volume",
    "成交额": "amount",
    "今开": "open",
    "最高": "high",
    "最低": "low",
    "昨收": "pre_close",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def fetch_spot_snapshot() -> pd.DataFrame:
    """拉 AKShare 全市场即时快照，返回标准化 DataFrame。

    列：symbol/code/name/price/change/pct_chg/volume/amount/open/high/low/pre_close/ts
    """
    import akshare as ak

    wait_for_rate_limit()
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise ValueError("empty spot snapshot")

    df.columns = [c.strip() for c in df.columns]
    keep_cols = [c for c in _QUOTE_COLS if c in df.columns]
    df = df[keep_cols].rename(columns=_QUOTE_COLS)

    def _norm(raw: object) -> str | None:
        try:
            return normalize(str(raw).zfill(6))
        except ValueError:
            return None

    df["symbol"] = df["code"].map(_norm)
    df = df.dropna(subset=["symbol"])
    df["ts"] = now_cn().isoformat()

    for col in ("price", "change", "pct_chg", "volume", "amount",
                "open", "high", "low", "pre_close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info("fetch_spot_snapshot: {} rows", len(df))
    return df


def build_quote_dict(row: pd.Series) -> dict:
    """单行 DataFrame → 推送给前端的 dict（去 NaN）。"""
    out: dict = {}
    for k, v in row.items():
        if pd.isna(v):
            continue
        out[k] = v.item() if hasattr(v, "item") else v
    return out


# ──────────────────────────────────────────────
# 单 symbol 实时报价（直调 eastmoney，避开 AKShare 分页限速）
# ──────────────────────────────────────────────

_SINGLE_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
# fltt=2 + invt=2 时 eastmoney 已返回 float-friendly 真实数值，不再缩放
_SINGLE_FIELDS = ",".join([
    "f43",   # 最新价 price
    "f44",   # 最高 high
    "f45",   # 最低 low
    "f46",   # 今开 open
    "f47",   # 成交量 volume（手）
    "f48",   # 成交额 amount（元）
    "f57",   # code
    "f58",   # name
    "f60",   # 昨收 pre_close
    "f169",  # 涨跌额 change
    "f170",  # 涨跌幅 pct_chg（百分比数值，如 -2.44）
])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
def fetch_single_quote(symbol: str) -> dict | None:
    """直调 eastmoney push2/api/qt/stock/get 拉单 symbol 实时报价。

    返回标准化 dict：symbol/code/name/price/change/pct_chg/volume/amount/
    open/high/low/pre_close/ts，找不到返回 None。
    """
    sym = normalize(symbol)
    raw_code = code(sym)
    # 用归一化前缀判定（sh 沪市 → 1；sz 深市 / bj 北交所 → 0）
    market = 1 if sym.startswith("sh") else 0
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": _SINGLE_FIELDS,
        "secid": f"{market}.{raw_code}",
    }
    wait_for_rate_limit()
    resp = _get_eastmoney_session().get(_SINGLE_QUOTE_URL, params=params, timeout=10)
    resp.raise_for_status()
    payload = resp.json() or {}
    data = payload.get("data") or {}
    if not data or data.get("f43") in (None, "-"):
        return None

    def _num(key: str) -> float | None:
        v = data.get(key)
        if v in (None, "-", ""):
            return None
        if not isinstance(v, (str, int, float)):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out: dict = {
        "symbol": sym,
        "code": str(data.get("f57") or raw_code),
        "name": data.get("f58"),
        "price": _num("f43"),
        "high": _num("f44"),
        "low": _num("f45"),
        "open": _num("f46"),
        "volume": _num("f47"),
        "amount": _num("f48"),
        "pre_close": _num("f60"),
        "change": _num("f169"),
        "pct_chg": _num("f170"),
        "ts": now_cn().isoformat(),
    }
    return {k: v for k, v in out.items() if v is not None}


def fetch_quotes(symbols: list[str]) -> list[dict]:
    """批量拉单 symbol 报价（串行，每条复用同一 Session 走限流）。"""
    results: list[dict] = []
    for sym in symbols:
        try:
            q = fetch_single_quote(sym)
            if q:
                results.append(q)
        except Exception as exc:
            logger.warning("fetch_single_quote {} failed: {}", sym, exc)
    return results
