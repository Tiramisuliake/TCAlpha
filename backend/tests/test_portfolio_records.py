"""组合回测存档模型测试（sync_db 建表 + CRUD）。

service 层（save/list/delete）为 AsyncSession 薄样板，项目无 async sqlite fixture，
此处以同步 session 验证模型定义 / JSON 字段 / 用户隔离查询语义。
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models.portfolio_record import PortfolioBacktestRecord
from app.db.models.user import User


def _mk_user(db, uid: int) -> None:
    db.add(User(id=uid, username=f"u{uid}", password_hash="x"))


def test_record_roundtrip_json_fields(sync_db):
    """插入 + 读回：config / metrics JSON 字段完整保留。"""
    with sync_db() as db:
        _mk_user(db, 1)
        db.add(PortfolioBacktestRecord(
            user_id=1, name="动量组合", kind="backtest",
            config={"top_n": 10, "weights": {"mom_20": 1.0}},
            metrics={"sharpe": 1.5, "total_return": 0.25},
        ))
        db.commit()

        row = db.execute(select(PortfolioBacktestRecord)).scalar_one()
        assert row.name == "动量组合"
        assert row.kind == "backtest"
        assert row.config["weights"]["mom_20"] == 1.0
        assert row.metrics["sharpe"] == 1.5
        assert row.created_at is not None


def test_records_user_isolation(sync_db):
    """按 user_id 过滤：各自只见自己的存档。"""
    with sync_db() as db:
        _mk_user(db, 1)
        _mk_user(db, 2)
        db.add(PortfolioBacktestRecord(user_id=1, name="a", config={}, metrics={}))
        db.add(PortfolioBacktestRecord(user_id=2, name="b", config={}, metrics={}))
        db.commit()

        mine = db.execute(
            select(PortfolioBacktestRecord).where(PortfolioBacktestRecord.user_id == 1)
        ).scalars().all()
        assert [r.name for r in mine] == ["a"]
