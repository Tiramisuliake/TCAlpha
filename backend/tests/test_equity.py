"""模拟账户净值快照（snapshot_equity_sync + snapshot_all_equity）单元测试。

用 sync_db（SQLite + 替换 SyncSessionLocal）+ fake_arctic（内存 bar_1d）。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest


def _seed_account(sync_db, user_id: int, balance: float) -> None:
    from app.db.models.account import SimAccount

    with sync_db() as db:
        db.add(SimAccount(user_id=user_id, balance=balance, init_capital=1_000_000.0))
        db.commit()


def _seed_filled_order(sync_db, user_id: int, symbol: str, price: float, volume: int) -> None:
    from app.db.models.order import SimOrder

    with sync_db() as db:
        db.add(SimOrder(
            user_id=user_id, symbol=symbol, direction="long", offset="open",
            price=price, volume=volume, filled_volume=volume, status="filled",
            created_at=datetime(2024, 1, 2, tzinfo=UTC),
            updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        ))
        db.commit()


def _write_close(fake_arctic, symbol: str, last_close: float) -> None:
    from app.db.arctic import get_library

    df = pd.DataFrame(
        {"close": [last_close - 1, last_close]},
        index=pd.date_range("2024-01-01", periods=2, freq="B", tz="Asia/Shanghai"),
    )
    get_library("bar_1d").write(symbol, df)


def test_snapshot_uses_market_value(sync_db, fake_arctic):
    """持仓市值按最新收盘价：现金 90 万 + 100 股 ×12 = 901200。"""
    from app.services.sim import snapshot_equity_sync

    _seed_account(sync_db, 1, balance=900_000.0)
    _seed_filled_order(sync_db, 1, "sh600000", price=10.0, volume=100)
    _write_close(fake_arctic, "sh600000", 12.0)

    snap = snapshot_equity_sync(1)
    assert snap is not None
    assert snap["balance"] == 900_000.0
    assert snap["position_value"] == 1200.0   # 100 × 12
    assert snap["total_asset"] == 901_200.0


def test_snapshot_falls_back_to_cost_when_no_quote(sync_db, fake_arctic):
    """ArcticDB 无该标的行情 → 持仓按成本均价 10 估值。"""
    from app.services.sim import snapshot_equity_sync

    _seed_account(sync_db, 1, balance=900_000.0)
    _seed_filled_order(sync_db, 1, "sh600000", price=10.0, volume=100)
    # 不写 arctic → 兜底成本

    snap = snapshot_equity_sync(1)
    assert snap["position_value"] == 1000.0   # 100 × 10（成本）
    assert snap["total_asset"] == 901_000.0


def test_snapshot_upsert_same_day(sync_db, fake_arctic):
    """同日两次快照 → upsert 覆盖，仅一行。"""
    from app.db.models.account import SimEquitySnapshot
    from app.services.sim import snapshot_equity_sync

    _seed_account(sync_db, 1, balance=1_000_000.0)
    snapshot_equity_sync(1)
    snapshot_equity_sync(1)

    with sync_db() as db:
        rows = db.query(SimEquitySnapshot).filter_by(user_id=1).all()
    assert len(rows) == 1
    assert rows[0].total_asset == 1_000_000.0   # 无持仓 = 纯现金


def test_snapshot_no_account_returns_none(sync_db, fake_arctic):
    from app.services.sim import snapshot_equity_sync

    assert snapshot_equity_sync(999) is None


async def test_attach_benchmark_aligns_and_normalizes(monkeypatch):
    """基准对齐归一化：指数按净值日期对齐、归一到净值起点，超额 = 净值收益 - 基准收益。"""
    import pandas as pd

    from app.schemas.sim import EquityCurveOut, EquityCurvePoint
    from app.services import sim as sim_svc

    points = [
        EquityCurvePoint(dt="2025-01-02", balance=0, position_value=0, total_asset=1_000_000.0),
        EquityCurvePoint(dt="2025-01-03", balance=0, position_value=0, total_asset=1_100_000.0),  # +10%
    ]
    # 指数同期 +5%（3000 → 3150）
    idx = pd.date_range("2025-01-02", periods=2, freq="D", tz="Asia/Shanghai")
    fake_series = pd.Series([3000.0, 3150.0], index=idx)
    monkeypatch.setattr(
        "app.core.backtest_engine._load_index_close", lambda *a, **k: fake_series
    )
    monkeypatch.setattr("app.core.backtest_engine._benchmark_name", lambda c: "沪深300")

    out = EquityCurveOut(init_capital=1_000_000.0, points=points)
    await sim_svc._attach_benchmark(out, points, "000300")

    assert out.benchmark == "沪深300"
    assert len(out.benchmark_points) == 2
    # 基准归一化到净值起点 100 万
    assert out.benchmark_points[0].value == pytest.approx(1_000_000.0)
    assert out.benchmark_points[1].value == pytest.approx(1_050_000.0)  # +5%
    # 超额 = 10% - 5% = 5%
    assert out.excess_return == pytest.approx(0.05, abs=1e-4)


async def test_attach_benchmark_skips_on_empty_index(monkeypatch):
    """指数加载为空 → 基准字段保持缺省，不报错。"""
    import pandas as pd

    from app.schemas.sim import EquityCurveOut, EquityCurvePoint
    from app.services import sim as sim_svc

    points = [
        EquityCurvePoint(dt="2025-01-02", balance=0, position_value=0, total_asset=1_000_000.0),
        EquityCurvePoint(dt="2025-01-03", balance=0, position_value=0, total_asset=1_100_000.0),
    ]
    monkeypatch.setattr(
        "app.core.backtest_engine._load_index_close", lambda *a, **k: pd.Series(dtype=float)
    )

    out = EquityCurveOut(init_capital=1_000_000.0, points=points)
    await sim_svc._attach_benchmark(out, points, "000300")

    assert out.benchmark is None
    assert out.benchmark_points == []


def test_snapshot_all_equity_task(sync_db, fake_arctic):
    """beat 任务遍历所有账户用户快照。"""
    from app.db.models.account import SimEquitySnapshot
    from app.tasks.sim_tasks import snapshot_all_equity

    _seed_account(sync_db, 1, balance=1_000_000.0)
    _seed_account(sync_db, 2, balance=500_000.0)

    res = snapshot_all_equity.run(force=True)
    assert res["status"] == "ok"
    assert res["count"] == 2

    with sync_db() as db:
        rows = db.query(SimEquitySnapshot).all()
    assert {r.user_id for r in rows} == {1, 2}
