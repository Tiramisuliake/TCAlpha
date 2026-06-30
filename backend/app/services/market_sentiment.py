"""市场情绪温度计：从全市场 spot 快照聚合大盘冷热指标。

平台第一个**择时**维度（区别于选股）：复用 screener 的全市场快照（含 pct_chg），
向量化算涨跌停家数 / 涨跌比 / 赚钱效应 / 情绪温度（0-100）。当前情绪实时读快照；
历史曲线由收盘 beat 每日存一行到 Redis hash（按日期去重），供前端画温度趋势。
"""
from __future__ import annotations

import io
import json

import pandas as pd

from app.db.redis_client import get_redis
from app.services.short_term import _board_limit_pct

_SENTIMENT_HIST_KEY = "market:sentiment:history"


def compute_sentiment(df: pd.DataFrame) -> dict:
    """从 spot 快照 DataFrame（含 symbol / pct_chg）算情绪指标。

    涨跌停按板块涨停线判定（主板 10% / 创业板·科创 20% / 北交所 30%，留 0.5% 容差）。
    温度 = 上涨家数 / 活跃家数（涨+跌）× 100：0 全跌、50 涨跌均衡、100 全涨。
    """
    neutral = {
        "total": 0, "up": 0, "down": 0, "flat": 0,
        "limit_up": 0, "limit_down": 0, "adv_decline_ratio": 0.0,
        "profit_effect": 0.0, "avg_pct_chg": 0.0, "temperature": 50,
    }
    if "pct_chg" not in df.columns or df.empty:
        return neutral
    pct = pd.to_numeric(df["pct_chg"], errors="coerce")
    total = int(pct.notna().sum())
    if total == 0:
        return neutral

    up = int((pct > 0).sum())
    down = int((pct < 0).sum())
    flat = total - up - down

    # 各票板块涨停线（百分比，留 0.5 容差）
    limit_line = df["symbol"].astype(str).map(lambda s: _board_limit_pct(s) * 100 - 0.5)
    limit_up = int((pct >= limit_line).sum())
    limit_down = int((pct <= -limit_line).sum())

    active = up + down
    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": flat,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "adv_decline_ratio": round(up / max(down, 1), 2),
        "profit_effect": round(up / total, 4),
        "avg_pct_chg": round(float(pct.mean()), 2),
        "temperature": round(up / max(active, 1) * 100),
    }


def _read_spot_df(raw: str) -> pd.DataFrame:
    return pd.read_json(io.StringIO(raw), dtype={"code": str, "symbol": str, "name": str})


async def get_current_sentiment() -> dict:
    """实时市场情绪：读 screener 全市场 spot 快照缓存 → 聚合指标。

    快照缺失时触发后台刷新并返回 ready=False（前端稍后重试）。
    """
    from app.services.screener import SNAPSHOT_KEY

    raw = await get_redis().get(SNAPSHOT_KEY)
    if not raw:
        from app.tasks.data_tasks import refresh_market_snapshot

        refresh_market_snapshot.delay()
        return {"ready": False}

    df = _read_spot_df(raw)
    if df.empty:
        return {"ready": False}
    return {"ready": True, **compute_sentiment(df)}


def snapshot_sentiment_sync() -> dict:
    """算当日情绪并存 Redis 历史（beat 调用，同步 redis）。按日期去重（覆盖当日）。"""
    import redis as sync_redis

    from app.config import settings
    from app.services.screener import SNAPSHOT_KEY
    from app.utils.trading_period import now_cn

    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = r.get(SNAPSHOT_KEY)
        if not raw:
            return {"ok": False, "reason": "no_snapshot"}
        s = compute_sentiment(_read_spot_df(raw))
        today = now_cn().strftime("%Y-%m-%d")
        r.hset(_SENTIMENT_HIST_KEY, today, json.dumps({"date": today, **s}, ensure_ascii=False))
    finally:
        r.close()
    return {"ok": True, "date": today, "temperature": s["temperature"]}


async def get_sentiment_history(days: int = 120) -> list[dict]:
    """读 Redis 情绪历史（按日期升序），取最近 days 天。"""
    raw = await get_redis().hgetall(_SENTIMENT_HIST_KEY)
    if not raw:
        return []
    points = [json.loads(v) for v in raw.values()]
    points.sort(key=lambda p: p.get("date", ""))
    return points[-days:]


def compute_limit_up_ladder(max_scan: int = 800) -> dict:
    """全市场连板梯队：扫历史日 K 算每票当前连板数，分档统计 + 最高板 + 高板龙头。

    复用 short_term 的连板判定（按板块涨停价）。连板情绪是打板资金活跃度的核心刻度——
    最高板代表市场情绪高度，连板家数代表参与广度。读 ArcticDB（同步 IO），路由层 to_thread。
    """
    from app.db.arctic import get_library
    from app.services.short_term import _board_limit_pct, _count_boards, _name_map

    empty = {"ready": False, "total": 0, "max_board": 0, "ladder": [], "leaders": []}
    lib = get_library("bar_1d")
    symbols = lib.list_symbols()
    if not symbols:
        return empty
    symbols = symbols[:max_scan]
    names = _name_map(symbols)

    counts: dict[int, int] = {}
    leaders: list[dict] = []
    for sym in symbols:
        try:
            df = lib.read(sym).data
        except Exception:
            continue
        if df is None or "close" not in df.columns or len(df) < 2:
            continue
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) < 2:
            continue
        boards = _count_boards(close, _board_limit_pct(sym))
        if boards < 1:
            continue
        counts[boards] = counts.get(boards, 0) + 1
        if boards >= 2:  # 2 板及以上为高板龙头
            code = sym[2:] if sym[:2] in ("sh", "sz", "bj") else sym
            leaders.append({"symbol": sym, "code": code, "name": names.get(sym, ""), "boards": boards})

    if not counts:
        return {**empty, "ready": True}

    buckets = {"1板": 0, "2板": 0, "3板": 0, "4板+": 0}
    for b, c in counts.items():
        key = f"{b}板" if b < 4 else "4板+"
        buckets[key] += c
    ladder = [{"label": k, "count": v} for k, v in buckets.items()]
    leaders.sort(key=lambda x: x["boards"], reverse=True)

    return {
        "ready": True,
        "total": sum(counts.values()),
        "max_board": max(counts),
        "ladder": ladder,
        "leaders": leaders[:20],
    }
