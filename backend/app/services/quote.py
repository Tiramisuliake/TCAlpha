"""实时报价服务（Phase 5 C 阶段）。

通过 AKShare 全市场快照 ``stock_zh_a_spot_em`` 拉取批量报价，按 symbol 推送到
Redis pub/sub。前端 ``/ws/quote?symbol=xxx`` 订阅对应 channel。

⚠️ 不在 endpoint 里直调，必须走 Celery（``app.tasks.data_tasks.push_quotes``）。
"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
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


def fetch_spot_snapshot() -> pd.DataFrame:
    """全市场即时报价快照 —— 委托统一 DataProvider（与选股共用快照，避免重复拉取）。

    列：symbol/code/name/price/change/pct_chg/volume/amount/open/high/low/pre_close/ts
    """
    from app.data import get_provider

    df = get_provider().fetch_market_spot()
    keep = [c for c in (
        "symbol", "code", "name", "price", "change", "pct_chg",
        "volume", "amount", "open", "high", "low", "pre_close",
    ) if c in df.columns]
    df = df[keep].copy()
    df["ts"] = now_cn().isoformat()
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


def fetch_single_quote(symbol: str) -> dict | None:
    """单 symbol 实时报价 —— 委托统一 DataProvider。"""
    from app.data import get_provider

    return get_provider().fetch_single_quote(symbol)


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
