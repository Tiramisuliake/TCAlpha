"""数据同步状态表 helper 测试（⑤）。

用 sync_db fixture（SQLite in-memory + patch SyncSessionLocal）覆盖 upsert/水位读取。
"""
from __future__ import annotations

from sqlalchemy import select

from app.tasks.data_tasks import _last_synced_date, _upsert_sync_log
from app.utils.symbol import normalize


def test_upsert_sync_log_insert_then_update(sync_db):
    from app.db.models.sync_log import SyncLog

    sym = normalize("sh600000")

    # 首次插入 ok
    _upsert_sync_log("sh600000", "1d", "ok", last_date="2025-01-10", rows=100)
    with sync_db() as db:
        row = db.execute(select(SyncLog).where(SyncLog.symbol == sym)).scalar_one()
        assert row.status == "ok"
        assert row.last_date == "2025-01-10"
        assert row.rows == 100

    # 同 (symbol, period) 再调 → 更新而非新增
    _upsert_sync_log("sh600000", "1d", "failed", error="boom")
    with sync_db() as db:
        rows = db.execute(select(SyncLog).where(SyncLog.symbol == sym)).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "failed"
        assert rows[0].error == "boom"


def test_last_synced_date(sync_db):
    # 无记录 → None
    assert _last_synced_date("sz000001", "1d") is None

    # ok 记录 → 返回 last_date
    _upsert_sync_log("sz000001", "1d", "ok", last_date="2025-02-01", rows=50)
    assert _last_synced_date("sz000001", "1d") == "2025-02-01"

    # failed 记录 → None（不作为增量起点，强制全量补）
    _upsert_sync_log("sz000001", "1d", "failed", error="x")
    assert _last_synced_date("sz000001", "1d") is None
