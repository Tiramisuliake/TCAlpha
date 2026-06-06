"""选股器：基于全市场快照按市值/PE/成交额/换手等条件筛选候选股。

数据：扩展 ``stock_zh_a_spot_em`` 保留市值/PE/换手率（quote.py 只留了价格类，丢了这些）。
快照由 Celery 刷新写 Redis（5min TTL）；``screen()`` 异步读缓存 + pandas 过滤，
避免在 endpoint 直调 AKShare。
"""
from __future__ import annotations

import io

import pandas as pd

from app.db.redis_client import get_redis

SNAPSHOT_KEY = "screener:snapshot:v1"
SNAPSHOT_TTL = 300  # 5 分钟


def fetch_screen_snapshot() -> pd.DataFrame:
    """全市场快照（含市值/PE/换手）—— 委托统一 DataProvider。"""
    from app.data import get_provider

    df = get_provider().fetch_market_spot()
    keep = [c for c in (
        "symbol", "code", "name", "price", "pct_chg",
        "amount", "turnover", "market_cap", "pe", "pb",
    ) if c in df.columns]
    return df[keep].copy()


def refresh_snapshot_cache_sync() -> int:
    """同步拉快照写 Redis（供 Celery 任务调用，用同步 redis 客户端）。返回行数。"""
    import redis as sync_redis

    from app.config import settings

    df = fetch_screen_snapshot()
    payload = df.to_json(orient="records", force_ascii=False)
    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(SNAPSHOT_KEY, payload, ex=SNAPSHOT_TTL)
    finally:
        r.close()
    return len(df)


async def screen(filters: dict) -> dict:
    """读 Redis 快照缓存 + pandas 过滤。缓存缺失则触发刷新并返回 ready=False。

    过滤项（均可选）：
      market_cap_min/max（亿元）· pe_min/max · amount_min（亿元）· turnover_min（%）
      · pct_chg_min/max（%）· exclude_st（bool）· sort_by（字段名）· limit（默认 50）
    """
    raw = await get_redis().get(SNAPSHOT_KEY)
    if not raw:
        # 缓存缺失/过期：触发后台刷新，前端稍后重试
        from app.tasks.data_tasks import refresh_market_snapshot

        refresh_market_snapshot.delay()
        return {"ready": False, "count": 0, "candidates": []}

    df = pd.read_json(io.StringIO(raw))
    if df.empty:
        return {"ready": True, "count": 0, "candidates": []}

    if (v := filters.get("market_cap_min")) is not None and "market_cap" in df:
        df = df[df["market_cap"] >= float(v) * 1e8]
    if (v := filters.get("market_cap_max")) is not None and "market_cap" in df:
        df = df[df["market_cap"] <= float(v) * 1e8]
    if (v := filters.get("pe_min")) is not None and "pe" in df:
        df = df[df["pe"] >= float(v)]
    if (v := filters.get("pe_max")) is not None and "pe" in df:
        df = df[df["pe"] <= float(v)]
    if (v := filters.get("amount_min")) is not None and "amount" in df:
        df = df[df["amount"] >= float(v) * 1e8]
    if (v := filters.get("turnover_min")) is not None and "turnover" in df:
        df = df[df["turnover"] >= float(v)]
    if (v := filters.get("pct_chg_min")) is not None and "pct_chg" in df:
        df = df[df["pct_chg"] >= float(v)]
    if (v := filters.get("pct_chg_max")) is not None and "pct_chg" in df:
        df = df[df["pct_chg"] <= float(v)]
    if filters.get("exclude_st"):
        df = df[~df["name"].astype(str).str.contains("ST", case=False, na=False)]

    sort_by = filters.get("sort_by") or "amount"
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)

    limit = int(filters.get("limit") or 50)
    records = df.head(limit).to_dict("records")
    # NaN → None，保证 JSON 可序列化
    candidates = [
        {k: (None if pd.isna(v) else v) for k, v in rec.items()} for rec in records
    ]
    return {"ready": True, "count": len(candidates), "candidates": candidates}
