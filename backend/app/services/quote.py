"""实时报价服务（Phase 5 C 阶段）。

通过 AKShare 全市场快照 ``stock_zh_a_spot_em`` 拉取批量报价，按 symbol 推送到
Redis pub/sub。前端 ``/ws/quote?symbol=xxx`` 订阅对应 channel。

⚠️ 不在 endpoint 里直调，必须走 Celery（``app.tasks.data_tasks.push_quotes``）。
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.data import wait_for_rate_limit
from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
from app.utils.symbol import normalize

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
    df["ts"] = datetime.now().isoformat()

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
