"""选股器路由（基于全市场快照按条件筛选）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.core.auth_deps import require_permission
from app.deps import CurrentUserId
from app.schemas.screener import (
    FactorICAllRequest,
    FactorICRequest,
    FactorICResult,
    FactorICSummary,
    FactorScreenRequest,
    LimitUpPremiumRequest,
    LimitUpPremiumResult,
    MatchPatternsRequest,
    PatternStatsAllRequest,
    PatternStatsRequest,
    PatternStatsResult,
    ResonanceRequest,
    ScreenRequest,
    ScreenResult,
    ShortTermRequest,
)
from app.services import factors as factors_svc
from app.services import screener as screener_svc
from app.services import short_term as short_term_svc

router = APIRouter()


@router.post(
    "/run",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_screen(
    payload: ScreenRequest,
    _: int = CurrentUserId,
):
    """按市值/PE/成交额/换手/涨跌幅等条件筛选候选股（读 Redis 全市场快照缓存）。"""
    return await screener_svc.screen(payload.model_dump())


@router.post(
    "/short-term",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_short_term(
    payload: ShortTermRequest,
    _: int = CurrentUserId,
):
    """短线技术选股：按量价形态（放量突破 / 均线多头 / 回踩企稳 / 涨停打板）扫描 ArcticDB 历史 K。

    扫描读 ArcticDB（同步 IO），丢线程池避免阻塞事件循环。
    """
    return await asyncio.to_thread(short_term_svc.scan_short_term, payload.model_dump())


@router.post(
    "/resonance",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_resonance(
    payload: ResonanceRequest,
    _: int = CurrentUserId,
):
    """多形态共振筛选：筛当前同时命中 ≥ min_patterns 个短线形态的强信号票。"""
    return await asyncio.to_thread(short_term_svc.scan_resonance, payload.model_dump())


@router.post(
    "/limit-up-premium",
    response_model=LimitUpPremiumResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_limit_up_premium(
    payload: LimitUpPremiumRequest,
    _: int = CurrentUserId,
):
    """涨停次日溢价统计（打板复盘）：扫历史涨停日，统计次日溢价 + 红盘率 + 按连板分组。"""
    return await asyncio.to_thread(
        short_term_svc.limit_up_premium, payload.symbol, payload.lookback
    )


@router.post(
    "/match-patterns",
    response_model=dict[str, list[str]],
    dependencies=[Depends(require_permission("data.read"))],
)
async def match_patterns(
    payload: MatchPatternsRequest,
    _: int = CurrentUserId,
):
    """对一组标的各算当前命中的短线形态（盯盘实时标记）。"""
    return await asyncio.to_thread(short_term_svc.match_patterns, payload.symbols)


@router.post(
    "/pattern-stats",
    response_model=PatternStatsResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def pattern_stats(
    payload: PatternStatsRequest,
    _: int = CurrentUserId,
):
    """形态前瞻收益统计：历史每次形态命中后持有 N 日的平均收益与胜率（验证形态有效性）。"""
    return await asyncio.to_thread(
        short_term_svc.pattern_forward_stats,
        payload.pattern, payload.symbol, payload.hold_days, payload.lookback,
    )


@router.post(
    "/pattern-stats-all",
    response_model=list[PatternStatsResult],
    dependencies=[Depends(require_permission("data.read"))],
)
async def pattern_stats_all(
    payload: PatternStatsAllRequest,
    _: int = CurrentUserId,
):
    """全形态前瞻收益对比：4 个短线形态各自命中后持有 N 日的收益与胜率，横向对比有效性。"""
    return await asyncio.to_thread(
        short_term_svc.pattern_forward_stats_all, payload.hold_days, payload.lookback
    )


@router.post(
    "/factor",
    response_model=ScreenResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_factor_screen(
    payload: FactorScreenRequest,
    _: int = CurrentUserId,
):
    """时序多因子选股：从历史日 K 算多周期动量 / 波动率 / 趋势斜率 / 量能因子，
    横截面 z-score 标准化后按方向加权综合打分排序。

    扫描读 ArcticDB（同步 IO），丢线程池避免阻塞事件循环。
    """
    return await asyncio.to_thread(factors_svc.factor_screen, payload.model_dump())


@router.post(
    "/factor-ic",
    response_model=FactorICResult,
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_factor_ic(
    payload: FactorICRequest,
    _: int = CurrentUserId,
):
    """单因子有效性检验：多采样时点横截面 rank IC + 5 档分层前瞻收益，
    回答某因子是否真有 alpha（IC 显著性 + 分层单调性 + 多空收益）。

    多时点切片重算因子（同步 IO + 计算），丢线程池避免阻塞事件循环。
    """
    return await asyncio.to_thread(
        factors_svc.factor_ic,
        payload.factor, payload.hold_days, payload.lookback,
        payload.sample_points, payload.max_scan,
    )


@router.post(
    "/factor-ic-all",
    response_model=list[FactorICSummary],
    dependencies=[Depends(require_permission("data.read"))],
)
async def run_factor_ic_all(
    payload: FactorICAllRequest,
    _: int = CurrentUserId,
):
    """全因子 IC 横评：一次遍历算所有因子的 IC + 多空收益，横向对比找最强因子。

    一个采样时点切片一次即得全因子（比单因子 ×N 省 IO），丢线程池避免阻塞。
    """
    return await asyncio.to_thread(
        factors_svc.factor_ic_all,
        payload.hold_days, payload.lookback, payload.sample_points, payload.max_scan,
    )
