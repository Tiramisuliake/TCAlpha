"""pytest 共享 fixture。

B 阶段（稳定性补强）加入：
- tmp_arctic：临时 LMDB ArcticDB 实例，每个测试隔离
- sample_bars_df：200 根金叉/死叉合成日 K
- sample_bars_arctic：将 sample_bars 写入临时 ArcticDB 的 bar_1d library
- sync_db：SQLite in-memory + 建表 + 替换 SyncSessionLocal
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ── ArcticDB mock library ─────────────────────────────────────────────


class _FakeReadResult:
    """模拟 ArcticDB read() 返回 VersionedItem，仅暴露 .data。"""

    def __init__(self, data: pd.DataFrame) -> None:
        self.data = data


class _FakeLib:
    """内存模拟 ArcticDB Library。"""

    def __init__(self) -> None:
        self._data: dict[str, pd.DataFrame] = {}

    def list_symbols(self) -> list[str]:
        return list(self._data.keys())

    def write(self, symbol: str, df: pd.DataFrame, **_kwargs) -> None:
        self._data[symbol] = df

    def append(self, symbol: str, df: pd.DataFrame, **_kwargs) -> None:
        if symbol in self._data:
            self._data[symbol] = pd.concat([self._data[symbol], df])
        else:
            self._data[symbol] = df

    def read(self, symbol: str, **_kwargs) -> _FakeReadResult:
        return _FakeReadResult(self._data[symbol])

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._data


@pytest.fixture
def fake_arctic(monkeypatch) -> Iterator[dict[str, _FakeLib]]:
    """Mock `app.db.arctic.get_library` 返回内存 FakeLib。

    避开 ArcticDB Windows LMDB 在临时目录的 UnicodeDecodeError bug；测试更纯净。
    yield 一个 {library_name: FakeLib} dict，便于测试断言。
    """
    from app.db import arctic as arctic_mod

    libs: dict[str, _FakeLib] = {}

    def fake_get_library(name: str) -> _FakeLib:
        if name not in libs:
            libs[name] = _FakeLib()
        return libs[name]

    monkeypatch.setattr(arctic_mod, "get_library", fake_get_library)
    yield libs


# 兼容旧别名（B2-B4 的测试用过 tmp_arctic）
@pytest.fixture
def tmp_arctic(fake_arctic) -> Iterator[dict[str, _FakeLib]]:
    yield fake_arctic


# ── 合成 K 线 ────────────────────────────────────────────────────────────


@pytest.fixture
def sample_bars_df() -> pd.DataFrame:
    """200 根日 K：缓跌 → 金叉上涨 → 高位震荡 → 死叉下跌。

    设计成 MaCrossStrategy(fast=10, slow=20) 必然金叉死叉各一次。
    """
    n = 200
    end = datetime(2025, 12, 31).date()
    dates = pd.bdate_range(end=end, periods=n, freq="B")

    closes = np.zeros(n)
    base = 10.0
    for i in range(n):
        if i < 60:
            closes[i] = base - i * 0.02
        elif i < 120:
            closes[i] = closes[59] + (i - 59) * 0.05
        elif i < 180:
            closes[i] = closes[119] + np.sin((i - 119) * 0.3) * 0.3
        else:
            closes[i] = closes[179] - (i - 179) * 0.04

    df = pd.DataFrame(index=dates)
    df.index = df.index.tz_localize("Asia/Shanghai")
    df["close"] = closes
    df["open"] = closes * 0.998
    df["high"] = closes * 1.005
    df["low"] = closes * 0.995
    df["volume"] = np.linspace(1e6, 3e6, n)
    df["amount"] = df["close"] * df["volume"]
    return df[["open", "high", "low", "close", "volume", "amount"]].astype(float)


@pytest.fixture
def sample_bars_arctic(fake_arctic, sample_bars_df) -> Iterator[str]:
    """把 sample_bars 写入 FakeLib bar_1d，symbol = sh600000。"""
    from app.db.arctic import get_library

    lib = get_library("bar_1d")
    lib.write("sh600000", sample_bars_df)
    yield "sh600000"


# ── 同步 DB session（SQLite in-memory）─────────────────────────────────


@pytest.fixture
def sync_db(monkeypatch) -> Iterator[sessionmaker]:
    """SQLite in-memory + create_all + 替换 SyncSessionLocal。

    覆盖 SimGateway / BacktestEngine 这种用 `SyncSessionLocal` 的代码。
    依赖：所有 ORM 模型必须能在 SQLite 上 create_all（无 JSONB / 无 PG 特定类型）。

    注意：`from app.db.postgres import SyncSessionLocal` 会在调用方模块拷一份
    引用，所以这里 patch 多个常见调用方的模块属性，确保替换生效。
    """
    import app.db.models  # noqa: F401 — 触发模型 register 到 Base.metadata
    from app.db import postgres as pg_mod
    from app.db.postgres import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    Base.metadata.create_all(engine)

    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pg_mod, "SyncSessionLocal", session_local)

    # 调用方模块也要 patch（from x import Y 拷了引用）
    for mod_path in (
        "app.core.sim_gateway",
        "app.core.backtest_engine",
        "app.core.runtime",
        "app.services.ai_watcher",
        "app.services.ai_alerts",
        "app.services.watchlist",
        "app.services.notify",
    ):
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            if hasattr(mod, "SyncSessionLocal"):
                monkeypatch.setattr(mod, "SyncSessionLocal", session_local)
        except ImportError:
            pass

    yield session_local
    engine.dispose()


# ── Bar 对象工厂（vnpy 不在 test 路径里也能用）──────────────────────────


@pytest.fixture
def make_bar():
    """工厂：make_bar(dt, open=, high=, low=, close=, volume=) → vnpy BarData。"""

    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import BarData

    def _make(
        dt: datetime,
        *,
        symbol: str = "sh600000",
        open_: float = 10.0,
        high: float = 10.5,
        low: float = 9.5,
        close: float = 10.0,
        volume: float = 1_000_000,
    ) -> BarData:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return BarData(
            symbol=symbol,
            exchange=Exchange.SSE,
            datetime=dt,
            interval=Interval.DAILY,
            open_price=open_,
            high_price=high,
            low_price=low,
            close_price=close,
            volume=volume,
            turnover=close * volume,
            gateway_name="TEST",
        )

    return _make
