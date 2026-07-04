"""短线选股 Celery 任务（每日收盘自动扫描 + 飞书推送）。

beat 在交易日收盘后触发 ``scan_short_term_daily``，跑短线技术选股，命中后
经事件总线 ``publish_event("screen.short_term")`` 广播 —— 用户在通知中心勾选
该事件类型即可收到飞书推送。无命中则不推送（减噪）。

收盘后已非交易时段，``is_trading_time`` 不适用；用工作日判断（beat cron 已限
day_of_week=1-5，任务内再保险一次）。法定节假日不精确，但当日无新数据时扫描
结果即前一交易日，影响有限。
"""
from __future__ import annotations

from loguru import logger

from app.core.event_bus import publish_event
from app.tasks.celery_app import celery_app
from app.utils.trading_period import now_cn

_PATTERN_CN = {
    "volume_breakout": "放量突破",
    "ma_long": "均线多头",
    "pullback": "回踩企稳",
    "limit_up": "涨停打板",
}

_DEFAULT_PATTERNS = ("volume_breakout", "ma_long", "pullback", "limit_up")


def _summary_payload(pattern: str, candidates: list[dict]) -> dict:
    """拼精简 payload（前 6 字段会平铺到飞书卡片）：形态 / 命中数 / TOP3 / 日期。"""
    payload: dict = {
        "形态": _PATTERN_CN.get(pattern, pattern),
        "命中": f"{len(candidates)} 只",
    }
    for i, c in enumerate(candidates[:3], 1):
        price = c.get("price")
        score = c.get("score")
        payload[f"TOP{i}"] = (
            f"{c.get('code', '')} {c.get('name', '')} "
            f"{price if price is not None else '-'}（动能 {score if score is not None else '-'}）"
        )
    payload["日期"] = now_cn().strftime("%Y-%m-%d")
    return payload


@celery_app.task(
    name="app.tasks.screen_tasks.scan_short_term_daily",
    bind=True,
    time_limit=600,
    soft_time_limit=540,
)
def scan_short_term_daily(
    self, pattern: str = "volume_breakout", top: int = 10, force: bool = False
) -> dict:
    """每日收盘短线选股扫描 + 命中推送。

    Args:
        pattern: 买点形态（volume_breakout / ma_long / pullback）
        top: 推送展示的命中数量上限
        force: True 跳过工作日判断（手动 / 调试）
    """
    if not force and now_cn().weekday() >= 5:
        logger.info("scan_short_term_daily: weekend, skip")
        return {"status": "skipped", "reason": "weekend"}

    from app.services.short_term import scan_short_term

    res = scan_short_term({"pattern": pattern, "limit": top})
    if not res.get("ready"):
        logger.info("scan_short_term_daily: no kline data, skip")
        return {"status": "skipped", "reason": "no_data"}

    candidates = res.get("candidates") or []
    if not candidates:
        # 无命中不推送，避免每日噪音
        logger.info("scan_short_term_daily[{}]: 0 hit", pattern)
        return {"status": "ok", "count": 0}

    publish_event(
        "screen.short_term",
        _summary_payload(pattern, candidates),
        level="info",
    )
    logger.info("scan_short_term_daily[{}]: {} hit, pushed", pattern, len(candidates))
    return {"status": "ok", "count": len(candidates)}


def _multi_summary(patterns: list[str], results: dict[str, list[dict]]) -> dict:
    """多形态汇总 payload：每个有命中的形态一行（命中数 + TOP3 代码名）；前 6 字段平铺飞书卡片。"""
    payload: dict = {}
    for pat in patterns:
        cands = results.get(pat) or []
        if not cands:
            continue
        names = " / ".join(
            f"{c.get('code', '')}{c.get('name', '')}" for c in cands[:3]
        )
        payload[_PATTERN_CN.get(pat, pat)] = f"{len(cands)} 只：{names}"
    payload["日期"] = now_cn().strftime("%Y-%m-%d")
    return payload


@celery_app.task(
    name="app.tasks.screen_tasks.scan_multi_pattern_daily",
    bind=True,
    time_limit=900,
    soft_time_limit=840,
)
def scan_multi_pattern_daily(
    self, patterns: list[str] | None = None, top: int = 5, force: bool = False
) -> dict:
    """每日收盘多形态合并扫描 + 一条汇总推送。

    逐形态跑 scan_short_term，把各形态命中汇总成单条 ``screen.short_term`` 事件
    （用户订阅同一事件即可），避免每形态各推一条。任一形态有数据即视为 ready；
    全形态零命中则不推送。

    Args:
        patterns: 形态列表，默认全部 4 形态
        top: 每形态展示的命中上限
        force: True 跳过工作日判断
    """
    if not force and now_cn().weekday() >= 5:
        logger.info("scan_multi_pattern_daily: weekend, skip")
        return {"status": "skipped", "reason": "weekend"}

    pats = list(patterns) if patterns else list(_DEFAULT_PATTERNS)

    from app.services.short_term import scan_short_term

    results: dict[str, list[dict]] = {}
    any_ready = False
    for pat in pats:
        res = scan_short_term({"pattern": pat, "limit": top})
        if res.get("ready"):
            any_ready = True
        results[pat] = res.get("candidates") or []

    if not any_ready:
        logger.info("scan_multi_pattern_daily: no kline data, skip")
        return {"status": "skipped", "reason": "no_data"}

    total = sum(len(v) for v in results.values())
    if total == 0:
        logger.info("scan_multi_pattern_daily: 0 hit across {} patterns", len(pats))
        return {"status": "ok", "count": 0}

    publish_event("screen.short_term", _multi_summary(pats, results), level="info")
    by_pattern = {p: len(c) for p, c in results.items()}
    logger.info("scan_multi_pattern_daily: {} hit, pushed {}", total, by_pattern)
    return {"status": "ok", "count": total, "by_pattern": by_pattern}


@celery_app.task(
    name="app.tasks.screen_tasks.refresh_factor_cache",
    bind=True,
    time_limit=600,
    soft_time_limit=540,
)
def refresh_factor_cache(self, max_scan: int = 800) -> dict:
    """每日收盘刷新全市场因子快照缓存（多因子选股命中后免全市场重算）。"""
    from app.services.factors import refresh_factor_cache_sync

    n = refresh_factor_cache_sync(max_scan)
    logger.info("refresh_factor_cache: {} symbols cached", n)
    return {"status": "ok", "cached": n}


@celery_app.task(
    name="app.tasks.screen_tasks.snapshot_market_sentiment",
    bind=True,
    time_limit=300,
    soft_time_limit=270,
)
def snapshot_market_sentiment(self, force: bool = False) -> dict:
    """每日收盘刷新全市场快照 + 存当日市场情绪温度（择时曲线）。"""
    if not force and now_cn().weekday() >= 5:
        logger.info("snapshot_market_sentiment: weekend, skip")
        return {"status": "skipped", "reason": "weekend"}

    from app.services.market_sentiment import snapshot_sentiment_sync
    from app.services.screener import refresh_snapshot_cache_sync

    refresh_snapshot_cache_sync()  # 先刷新 spot 快照，确保用收盘数据
    res = snapshot_sentiment_sync()
    logger.info("snapshot_market_sentiment: {}", res)

    # 顺带推送当日综合择时信号（仓位建议）；推送失败不拖垮存档结果
    if res.get("ok"):
        try:
            _push_timing_signal()
        except Exception as exc:
            logger.warning("push timing signal failed: {}", exc)
    return {"status": "ok", **res}


def _push_timing_signal() -> None:
    """收盘后合成并推送综合择时信号（北向缺失自动降级权重）。"""
    import json as _json

    import redis as sync_redis

    from app.config import settings
    from app.services.market_sentiment import (
        _NORTH_TODAY_KEY,
        _SENTIMENT_HIST_KEY,
        _compose_timing,
    )

    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        today = now_cn().strftime("%Y-%m-%d")
        senti_raw = r.hget(_SENTIMENT_HIST_KEY, today)
        north_raw = r.get(_NORTH_TODAY_KEY)
    finally:
        r.close()
    if not senti_raw:
        return
    north = _json.loads(north_raw) if north_raw else None
    sig = _compose_timing(_json.loads(senti_raw), north["net"] if north else None)
    publish_event(
        "market.timing",
        {
            "仓位建议": f"{sig['level']}（{sig['score']} 分）",
            "解读": sig["advice"],
            **{p["name"]: f"{p['score']} 分" for p in sig["parts"]},
            "日期": today,
        },
        level="info",
    )


@celery_app.task(name="app.tasks.screen_tasks.refresh_north_flow", bind=True, time_limit=120)
def refresh_north_flow(self) -> dict:
    """盘中刷新北向资金净流入（接口不可用时优雅降级）。"""
    from app.services.market_sentiment import fetch_north_flow_sync

    res = fetch_north_flow_sync()
    logger.info("refresh_north_flow: {}", res)
    return {"status": "ok", **res}


@celery_app.task(name="app.tasks.screen_tasks.refresh_industry_boards", bind=True, time_limit=120)
def refresh_industry_boards(self) -> dict:
    """盘中刷新行业板块涨跌排行（接口不可用时优雅降级）。"""
    from app.services.market_sentiment import fetch_industry_boards_sync

    res = fetch_industry_boards_sync()
    logger.info("refresh_industry_boards: {}", res)
    return {"status": "ok", **res}


def _factor_summary(candidates: list[dict]) -> dict:
    """多因子选股汇总 payload：命中数 + TOP3（代码名 + 综合分）；前 6 字段平铺飞书卡片。"""
    payload: dict = {"策略": "多因子综合", "命中": f"{len(candidates)} 只"}
    for i, c in enumerate(candidates[:3], 1):
        score = c.get("score")
        payload[f"TOP{i}"] = (
            f"{c.get('code', '')} {c.get('name', '')}"
            f"（综合分 {score if score is not None else '-'}）"
        )
    payload["日期"] = now_cn().strftime("%Y-%m-%d")
    return payload


@celery_app.task(
    name="app.tasks.screen_tasks.factor_screen_daily",
    bind=True,
    time_limit=600,
    soft_time_limit=540,
)
def factor_screen_daily(self, top: int = 10, force: bool = False) -> dict:
    """每日收盘多因子选股 top N + 推送（系统默认权重，命中因子快照缓存秒级返回）。

    用默认权重综合打分，把 top N 经 ``screen.factor`` 事件推送 —— 用户在通知中心
    勾选该事件即可收飞书。无候选不推（减噪）。收盘后用工作日判断（beat cron 已限工作日）。

    Args:
        top: 推送展示的候选数量上限
        force: True 跳过工作日判断（手动 / 调试）
    """
    if not force and now_cn().weekday() >= 5:
        logger.info("factor_screen_daily: weekend, skip")
        return {"status": "skipped", "reason": "weekend"}

    from app.services.factors import factor_screen

    res = factor_screen({"limit": top})
    if not res.get("ready"):
        logger.info("factor_screen_daily: no kline data, skip")
        return {"status": "skipped", "reason": "no_data"}

    candidates = res.get("candidates") or []
    if not candidates:
        logger.info("factor_screen_daily: 0 candidate")
        return {"status": "ok", "count": 0}

    publish_event("screen.factor", _factor_summary(candidates), level="info")
    logger.info("factor_screen_daily: {} candidates, pushed", len(candidates))
    return {"status": "ok", "count": len(candidates)}
