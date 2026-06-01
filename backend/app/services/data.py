"""AKShare 数据下载 + ArcticDB 落库（Phase 1）。"""
from __future__ import annotations

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.db.arctic import get_library
from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
from app.utils.rate_limit import acquire, wait_for_akshare
from app.utils.symbol import code, normalize
from app.utils.trading_period import now_cn


def wait_for_rate_limit(max_per_sec: int | None = None) -> None:
    """向后兼容封装：转发到 utils.rate_limit。"""
    if max_per_sec is not None:
        acquire("ak", max_per_sec)
    else:
        wait_for_akshare()


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
        metadata={"source": "akshare", "fetched_at": now_cn().isoformat()},
    )
    rows = len(combined)
    logger.info("save_daily: {} → {} rows total", sym_key, rows)
    return rows


def download_and_save_daily(symbol: str, start: str, end: str) -> dict:
    """下载并落库，返回摘要 dict（供 Celery 任务直接调用）。"""
    df = fetch_daily(symbol, start, end)
    rows = save_daily(symbol, df)
    return {"symbol": normalize(symbol), "rows": rows, "start": start, "end": end}


# ──────────────────────────────────────────────
# 分钟 K 线（Phase 5 C 阶段）
# ──────────────────────────────────────────────

_MINUTE_PERIODS = (1, 5, 15, 30, 60)
_MINUTE_COLS = ["open", "high", "low", "close", "volume", "amount"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_minute_kline(
    symbol: str,
    period: int,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """从 AKShare 下载分钟 K，period ∈ {1,5,15,30,60}。

    AKShare ``stock_zh_a_hist_min_em`` 要求 symbol 用 ``sh600000`` 格式，period 传字符串。
    start/end 格式 ``YYYY-MM-DD HH:MM:SS``；不传则取近一段（AKShare 默认窗口）。
    """
    if period not in _MINUTE_PERIODS:
        raise ValueError(f"unsupported minute period: {period}, allowed {_MINUTE_PERIODS}")

    import akshare as ak

    wait_for_rate_limit()
    sym_key = normalize(symbol)
    raw_code = code(sym_key)
    kwargs: dict = {
        "symbol": raw_code,
        "period": str(period),
        "adjust": "qfq",
    }
    if start:
        kwargs["start_date"] = start
    if end:
        kwargs["end_date"] = end

    df = ak.stock_zh_a_hist_min_em(**kwargs)
    if df is None or df.empty:
        raise ValueError(f"empty minute data for {symbol} period={period}")

    df.columns = [c.strip() for c in df.columns]
    rename_map = {
        "时间": "dt", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "amount",
    }
    df = df.rename(columns=rename_map)

    df["dt"] = pd.to_datetime(df["dt"]).dt.tz_localize("Asia/Shanghai")
    df = df.set_index("dt").sort_index()

    for col in _MINUTE_COLS:
        if col not in df.columns:
            df[col] = 0.0
    df = df[_MINUTE_COLS].astype(float)

    if df["close"].isna().any():
        raise ValueError(f"NaN in close price for {symbol} period={period}")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"index not monotonic for {symbol} period={period}")
    if df.index.duplicated().any():
        df = df[~df.index.duplicated(keep="last")]

    return df


def save_minute(symbol: str, period: int, df: pd.DataFrame) -> int:
    """增量写入 ArcticDB ``bar_{period}m`` library，返回总行数。"""
    if period not in _MINUTE_PERIODS:
        raise ValueError(f"unsupported minute period: {period}")

    lib = get_library(f"bar_{period}m")
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
        metadata={
            "source": "akshare",
            "period": f"{period}m",
            "fetched_at": now_cn().isoformat(),
        },
    )
    rows = len(combined)
    logger.info("save_minute: {} [{}m] → {} rows total", sym_key, period, rows)
    return rows


def download_and_save_minute(
    symbol: str,
    period: int,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """下载并落库分钟 K，返回摘要 dict（供 Celery 任务直接调用）。"""
    df = fetch_minute_kline(symbol, period, start, end)
    rows = save_minute(symbol, period, df)
    return {
        "symbol": normalize(symbol),
        "period": f"{period}m",
        "rows": rows,
        "start": start,
        "end": end,
    }
