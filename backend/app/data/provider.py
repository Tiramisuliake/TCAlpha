"""统一数据获取层（DataProvider）。

把原本散落在 ``services/data|quote|screener`` 的 AKShare 调用收口到单一 Provider：
统一限流、重试、字段映射、symbol 适配。最大收益是 ``stock_zh_a_spot_em`` 全市场快照
原本被 fetch_symbol_list / fetch_spot_snapshot / fetch_screen_snapshot 各拉一次（3 次），
现统一走 ``fetch_market_spot()`` 一次拉全字段，三方各取所需。

未来换源（Tushare 等）只需实现一个新的 Provider 并改 ``get_provider()``，业务层不动。
当前仅 ``AkshareProvider``，纯 AKShare、无需任何付费 token。
"""
from __future__ import annotations

from typing import Protocol

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils import akshare_compat  # noqa: F401  # 注入 UA 补丁
from app.utils.akshare_compat import _get_eastmoney_session
from app.utils.rate_limit import wait_for_akshare
from app.utils.symbol import code, normalize
from app.utils.trading_period import now_cn

# ── 列映射 / 常量 ──────────────────────────────────────────────────────

# 全市场快照：保留超集列，供 symbol_list / quote / screener 各取所需
_SPOT_COLS = {
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
    "换手率": "turnover",
    "总市值": "market_cap",
    "市盈率-动态": "pe",
    "市净率": "pb",
}
_SPOT_NUMERIC = (
    "price", "change", "pct_chg", "volume", "amount", "open", "high", "low",
    "pre_close", "turnover", "market_cap", "pe", "pb",
)

_DAILY_COLS = ["open", "high", "low", "close", "volume", "amount"]
_MINUTE_PERIODS = (1, 5, 15, 30, 60)
_MINUTE_COLS = ["open", "high", "low", "close", "volume", "amount"]

_SINGLE_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_SINGLE_FIELDS = ",".join([
    "f43", "f44", "f45", "f46", "f47", "f48", "f57", "f58", "f60", "f169", "f170",
])


def _safe_norm(raw: object) -> str | None:
    try:
        return normalize(str(raw).zfill(6))
    except ValueError:
        return None


# ── Protocol ───────────────────────────────────────────────────────────

class DataProvider(Protocol):
    """数据源契约。换源时实现同名方法即可。"""

    def fetch_market_spot(self) -> pd.DataFrame: ...
    def fetch_symbol_list(self) -> list[dict]: ...
    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame: ...
    def fetch_index_daily(self, index_code: str, start: str, end: str) -> pd.DataFrame: ...
    def fetch_minute_kline(
        self, symbol: str, period: int, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame: ...
    def fetch_single_quote(self, symbol: str) -> dict | None: ...


# ── AKShare 实现 ───────────────────────────────────────────────────────

class AkshareProvider:
    """基于 AKShare 的数据源实现（免费，无 token）。"""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def fetch_market_spot(self) -> pd.DataFrame:
        """拉全市场即时快照（含价格/市值/PE/换手），标准化为英文列 + symbol。

        这是 symbol_list / spot 报价 / 选股 三方的单一来源，避免重复拉取。
        """
        import akshare as ak

        wait_for_akshare()
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            raise ValueError("empty spot snapshot")

        df.columns = [c.strip() for c in df.columns]
        keep = [c for c in _SPOT_COLS if c in df.columns]
        df = df[keep].rename(columns=_SPOT_COLS)
        df["symbol"] = df["code"].map(_safe_norm)
        df = df.dropna(subset=["symbol"])
        for col in _SPOT_NUMERIC:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info("fetch_market_spot: {} rows", len(df))
        return df

    def fetch_symbol_list(self) -> list[dict]:
        """全市场股票列表（从 fetch_market_spot 派生，不再单独拉一次）。"""
        df = self.fetch_market_spot()
        result: list[dict] = []
        for sym, name in zip(df["symbol"], df["name"], strict=False):
            result.append({
                "symbol": sym,
                "code": code(sym),
                "exchange": sym[:2].upper(),
                "name": name,
            })
        logger.info("fetch_symbol_list: {} symbols", len(result))
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """日 K（前复权），DatetimeIndex(Asia/Shanghai)。"""
        import akshare as ak

        wait_for_akshare()
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

        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={
            "日期": "dt", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
        })
        df["dt"] = pd.to_datetime(df["dt"]).dt.tz_localize("Asia/Shanghai")
        df = df.set_index("dt").sort_index()
        for col in _DAILY_COLS:
            if col not in df.columns:
                df[col] = 0.0
        df = df[_DAILY_COLS].astype(float)

        if df["close"].isna().any():
            raise ValueError(f"NaN in close price for {symbol}")
        if not df.index.is_monotonic_increasing:
            raise ValueError(f"index not monotonic for {symbol}")
        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch_index_daily(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        """指数日 K，DatetimeIndex(Asia/Shanghai)。index_code 如 '000300'（沪深300）。

        指数无复权概念，取原始 OHLCV；列对齐个股 _DAILY_COLS 便于回测基准复用。
        """
        import akshare as ak

        wait_for_akshare()
        df = ak.index_zh_a_hist(
            symbol=index_code,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
        )
        if df is None or df.empty:
            raise ValueError(f"empty index data for {index_code} [{start}~{end}]")

        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={
            "日期": "dt", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
        })
        df["dt"] = pd.to_datetime(df["dt"]).dt.tz_localize("Asia/Shanghai")
        df = df.set_index("dt").sort_index()
        for col in _DAILY_COLS:
            if col not in df.columns:
                df[col] = 0.0
        df = df[_DAILY_COLS].astype(float)

        if df["close"].isna().any():
            raise ValueError(f"NaN in close price for index {index_code}")
        if not df.index.is_monotonic_increasing:
            raise ValueError(f"index not monotonic for index {index_code}")
        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch_minute_kline(
        self, symbol: str, period: int, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        """分钟 K（前复权），period ∈ {1,5,15,30,60}。"""
        if period not in _MINUTE_PERIODS:
            raise ValueError(f"unsupported minute period: {period}, allowed {_MINUTE_PERIODS}")

        import akshare as ak

        wait_for_akshare()
        raw_code = code(normalize(symbol))
        kwargs: dict = {"symbol": raw_code, "period": str(period), "adjust": "qfq"}
        if start:
            kwargs["start_date"] = start
        if end:
            kwargs["end_date"] = end

        df = ak.stock_zh_a_hist_min_em(**kwargs)
        if df is None or df.empty:
            raise ValueError(f"empty minute data for {symbol} period={period}")

        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={
            "时间": "dt", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
        })
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def fetch_single_quote(self, symbol: str) -> dict | None:
        """单 symbol 实时报价（直调 eastmoney，避开 AKShare 分页限速）。"""
        sym = normalize(symbol)
        raw_code = code(sym)
        market = 1 if sym.startswith("sh") else 0
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": _SINGLE_FIELDS,
            "secid": f"{market}.{raw_code}",
        }
        wait_for_akshare()
        resp = _get_eastmoney_session().get(_SINGLE_QUOTE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        if not data or data.get("f43") in (None, "-"):
            return None

        def _num(key: str) -> float | None:
            v = data.get(key)
            if v in (None, "-", "") or not isinstance(v, (str, int, float)):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        out = {
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


_provider: DataProvider | None = None


def get_provider() -> DataProvider:
    """返回数据源单例。换源时改这里即可。"""
    global _provider
    if _provider is None:
        _provider = AkshareProvider()
    return _provider
