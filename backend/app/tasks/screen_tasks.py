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
