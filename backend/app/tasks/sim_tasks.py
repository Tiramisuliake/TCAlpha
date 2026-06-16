"""模拟账户 Celery 任务（每日收盘后净值快照）。

beat 在交易日收盘后遍历所有有资金账户的用户，快照当日净值（现金 + 持仓市值）
落 sim_equity_snapshots，供 Trade 页净值曲线复盘。同步 SyncSession，工作日判断
（cron 已限 day_of_week=1-5）。
"""
from __future__ import annotations

from loguru import logger

from app.tasks.celery_app import celery_app
from app.utils.trading_period import now_cn


@celery_app.task(
    name="app.tasks.sim_tasks.snapshot_all_equity",
    bind=True,
    time_limit=600,
    soft_time_limit=540,
)
def snapshot_all_equity(self, force: bool = False) -> dict:
    """遍历所有 SimAccount 用户，快照当日净值。"""
    if not force and now_cn().weekday() >= 5:
        logger.info("snapshot_all_equity: weekend, skip")
        return {"status": "skipped", "reason": "weekend"}

    from sqlalchemy import select

    from app.db.models.account import SimAccount
    from app.db.postgres import SyncSessionLocal
    from app.services.sim import snapshot_equity_sync

    with SyncSessionLocal() as db:
        user_ids = db.execute(select(SimAccount.user_id)).scalars().all()

    ok = 0
    for uid in user_ids:
        try:
            if snapshot_equity_sync(uid) is not None:
                ok += 1
        except Exception:
            logger.exception("snapshot_all_equity: user={} failed", uid)

    logger.info("snapshot_all_equity: {}/{} snapshotted", ok, len(user_ids))
    return {"status": "ok", "count": ok, "total": len(user_ids)}
