"""AKShare 数据下载 + ArcticDB 落库（Phase 1）。"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import redis as _redis
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.db.arctic import get_library
from app.utils.symbol import code, normalize

_r = _redis.from_url(settings.redis_url, decode_responses=True)

# ──────────────────────────────────────────────
# 限流（Redis 令牌，跨 worker 共享）
# ──────────────────────────────────────────────

def wait_for_rate_limit(max_per_sec: int | None = None) -> None:
    limit = max_per_sec or settings.akshare_rate_limit
    while True:
        slot = int(time.time())
        key = f"ak:slot:{slot}"
        cnt = int(_r.incr(key))
        if cnt == 1:
            _r.expire(key, 2)
        if cnt <= limit:
            return
        time.sleep(0.3)


# ──────────────────────────────────────────────
# 股票列表
# ──────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def fetch_symbol_list() -> list[dict]:
    """从 AKShare 拉全市场股票列表，返回标准化 dict 列表。"""
    import akshare as ak

    wait_for_rate_limit()
    df = ak.stock_zh_a_spot_em()
    # 原始列：代码 名称 最新价 涨跌幅 ...
    df = df[["代码", "名称"]].copy()
    df.columns = ["code", "name"]

    result: list[dict] = []
    for _, row in df.iterrows():
        raw_code: str = str(row["code"]).zfill(6)
        try:
            sym = normalize(raw_code)
        except ValueError:
            continue
        result.append({
            "symbol": sym,
            "code": code(sym),
            "exchange": sym[:2].upper(),
            "name": row["name"],
        })
    logger.info("fetch_symbol_list: {} symbols", len(result))
    return result


# ──────────────────────────────────────────────
# 日 K 线
# ──────────────────────────────────────────────

_DAILY_COLS = ["open", "high", "low", "close", "volume", "amount"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    """从 AKShare 下载日 K，返回 DatetimeIndex DataFrame（Asia/Shanghai）。"""
    import akshare as ak

    wait_for_rate_limit()
    raw_code = code(normalize(symbol))
    df = ak.stock_zh_a_hist(
        symbol=raw_code,
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    if df is None or df.empty:
        raise ValueError(f"empty data for {symbol} [{start}~{end}]")

    # 列名适配（AKShare 可能因版本变化）
    df.columns = [c.strip() for c in df.columns]
    rename_map = {
        "日期": "dt", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
    }
    df = df.rename(columns=rename_map)

    df["dt"] = pd.to_datetime(df["dt"]).dt.tz_localize("Asia/Shanghai")
    df = df.set_index("dt").sort_index()

    for col in _DAILY_COLS:
        if col not in df.columns:
            df[col] = 0.0
    df = df[_DAILY_COLS].astype(float)

    # 数据完整性校验
    if df["close"].isna().any():
        raise ValueError(f"NaN in close price for {symbol}")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"index not monotonic for {symbol}")

    return df


def save_daily(symbol: str, df: pd.DataFrame) -> int:
    """增量写入 ArcticDB bar_1d library，返回写入行数。"""
    lib = get_library("bar_1d")
    sym_key = normalize(symbol)

    if sym_key in lib.list_symbols():
        existing: pd.DataFrame = lib.read(sym_key).data
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = df

    lib.write(
        sym_key,
        combined,
        metadata={"source": "akshare", "fetched_at": datetime.now().isoformat()},
    )
    rows = len(combined)
    logger.info("save_daily: {} → {} rows total", sym_key, rows)
    return rows


def download_and_save_daily(symbol: str, start: str, end: str) -> dict:
    """下载并落库，返回摘要 dict（供 Celery 任务直接调用）。"""
    df = fetch_daily(symbol, start, end)
    rows = save_daily(symbol, df)
    return {"symbol": normalize(symbol), "rows": rows, "start": start, "end": end}
