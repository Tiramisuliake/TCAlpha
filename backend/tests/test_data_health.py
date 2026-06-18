"""数据健康聚合（data_health_sync）单元测试。

sync_db（SQLite + 替换 SyncSessionLocal）+ fake_arctic（内存 bar_1d）。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd


def _seed_symbol(sync_db, symbol: str, *, active: bool = True) -> None:
    from app.db.models.symbol import Symbol

    with sync_db() as db:
        db.add(Symbol(
            symbol=symbol, code=symbol[2:], exchange=symbol[:2].upper(),
            name=symbol, is_active=active,
        ))
        db.commit()


def _seed_synclog(sync_db, symbol: str, status: str, error: str | None = None) -> None:
    from app.db.models.sync_log import SyncLog

    with sync_db() as db:
        db.add(SyncLog(
            symbol=symbol, period="1d", status=status, last_date="2026-06-12",
            rows=100, error=error, updated_at=datetime(2026, 6, 12, tzinfo=UTC),
        ))
        db.commit()


def test_data_health_coverage_and_sync(sync_db, fake_arctic):
    """覆盖率 = bar_1d 覆盖数 / 活跃 symbols；同步 ok/failed 计数 + 失败明细。"""
    from app.db.arctic import get_library
    from app.services.data import data_health_sync

    # 2 只活跃股票，其中 1 只有 bar_1d 数据
    _seed_symbol(sync_db, "sh600000")
    _seed_symbol(sync_db, "sz000001")
    df = pd.DataFrame({"close": [10.0, 11.0]},
                      index=pd.date_range("2026-06-11", periods=2, tz="Asia/Shanghai"))
    get_library("bar_1d").write("sh600000", df)

    _seed_synclog(sync_db, "sh600000", "ok")
    _seed_synclog(sync_db, "sz000001", "failed", error="empty data")

    res = data_health_sync()

    assert res["symbols_total"] == 2
    assert res["bar1d_covered"] == 1
    assert res["coverage_rate"] == 0.5
    assert res["sync_ok"] == 1
    assert res["sync_failed"] == 1
    assert len(res["recent_failures"]) == 1
    assert res["recent_failures"][0]["symbol"] == "sz000001"
    assert "empty data" in res["recent_failures"][0]["error"]


def test_data_health_empty(sync_db, fake_arctic):
    """空库：总数 0、覆盖率 0、无失败。"""
    from app.services.data import data_health_sync

    res = data_health_sync()
    assert res["symbols_total"] == 0
    assert res["bar1d_covered"] == 0
    assert res["coverage_rate"] == 0.0
    assert res["recent_failures"] == []
