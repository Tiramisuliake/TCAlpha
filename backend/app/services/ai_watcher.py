"""AI 盯盘核心（Phase 5 Step 3）。

流程：
  1. 读 ArcticDB bar_1d 最近 60 根
  2. 算 MA5/10/20、RSI14、MACD、最近 5 日涨跌幅
  3. 拼 prompt 喂 AI（system 要求严格 JSON）
  4. JSON 严格校验 → 落 ai_alerts → publish_event("ai.alert.{level}")
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from openai import APIError
from pydantic import ValidationError
from sqlalchemy import select

from app.config import settings
from app.core.event_bus import publish_event
from app.db.models.ai_alert import AiAlert
from app.db.models.watchlist import Watchlist
from app.db.postgres import SyncSessionLocal
from app.schemas.ai_alert import WatchResult
from app.services.ai import get_client
from app.utils.symbol import normalize

_SYSTEM_PROMPT = """你是 TCAlpha A 股技术分析师。仅基于用户给的指标快照做客观判断，输出严格 JSON。

规则：
- level: "info" = 中性 / 偏多偏空但不强；"warn" = 明显信号，建议关注；"danger" = 强信号，建议立刻处理
- signal: 一句话不超过 50 字
- reason: 200-400 字，包含趋势 / 关键位 / 短期信号 / 风险点四要素
- 严禁推测当下价格未来走势的概率；只描述已有指标含义
- 严禁输出"建议买入/卖出"等可被视为投资建议的语句，改为"短线偏强 / 谨慎"等中性表述
- 必须返回 JSON 对象，不要 Markdown 代码块，不要解释性前言
"""


# ── 技术指标 ──────────────────────────────────────────────────────────


def _rsi(close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return float("nan")
    delta = np.diff(close[-period - 1 :])
    gain = np.where(delta > 0, delta, 0).mean()
    loss = np.where(delta < 0, -delta, 0).mean()
    if loss == 0:
        return 100.0
    rs = gain / loss
    return float(100 - 100 / (1 + rs))


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _macd(close: np.ndarray) -> tuple[float, float, float]:
    if len(close) < 35:
        return (float("nan"),) * 3
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    hist = (dif - dea) * 2
    return float(dif[-1]), float(dea[-1]), float(hist[-1])


# ── 快照 ──────────────────────────────────────────────────────────────


_VALID_PERIODS = {"1d", "1m", "5m", "15m", "30m", "60m"}


def build_snapshot(symbol: str, period: str = "1d") -> dict[str, Any] | None:
    """从 ArcticDB 读最近 60 根 K，算指标，返回喂给 AI 的字典。

    period: 1d / 1m / 5m / 15m / 30m / 60m，对应 ``bar_{period}`` library。
    """
    if period not in _VALID_PERIODS:
        logger.warning("ai_watcher: invalid period {}", period)
        return None

    from app.db.arctic import get_library

    sym = normalize(symbol)
    lib_name = f"bar_{period}"
    lib = get_library(lib_name)
    if sym not in lib.list_symbols():
        logger.warning("ai_watcher: no {} data for {}", lib_name, sym)
        return None

    df: pd.DataFrame = lib.read(sym).data
    if df.empty:
        return None
    df = df.tail(60)

    close = df["close"].to_numpy(dtype=float)
    if len(close) < 25:
        logger.warning("ai_watcher: {} only {} bars, skip", sym, len(close))
        return None

    ma5 = float(close[-5:].mean())
    ma10 = float(close[-10:].mean())
    ma20 = float(close[-20:].mean())
    rsi = _rsi(close, 14)
    dif, dea, hist = _macd(close)

    recent_close = [round(float(x), 2) for x in close[-5:]]
    ret_5d = float(close[-1] / close[-6] - 1) if len(close) >= 6 else 0.0
    ret_20d = float(close[-1] / close[-21] - 1) if len(close) >= 21 else 0.0

    last_idx = df.index[-1]
    as_of = str(last_idx.date()) if period == "1d" else last_idx.isoformat()
    snapshot = {
        "symbol": sym,
        "period": period,
        "as_of": as_of,
        "close": round(float(close[-1]), 2),
        "recent_close_5d": recent_close,
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "rsi14": round(rsi, 2),
        "macd_dif": round(dif, 3),
        "macd_dea": round(dea, 3),
        "macd_hist": round(hist, 3),
        "ret_5d_pct": round(ret_5d * 100, 2),
        "ret_20d_pct": round(ret_20d * 100, 2),
        "vol_avg_5d": round(float(df["volume"].tail(5).mean()), 0),
        "vol_last": round(float(df["volume"].iloc[-1]), 0),
    }
    return snapshot


# ── AI 调用 ──────────────────────────────────────────────────────────


def _call_ai_json(snapshot: dict[str, Any]) -> WatchResult | None:
    """单次非流式调用，要求 JSON 输出。同步包装异步 client。"""
    import asyncio

    user_prompt = (
        "下面是某 A 股最近 60 个交易日的技术指标快照，请输出 JSON：\n```json\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2)
        + "\n```"
    )

    async def _call() -> WatchResult | None:
        try:
            resp = await get_client().chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=30.0,
            )
        except APIError as exc:
            logger.warning("ai_watcher: APIError {}", exc)
            return None
        except Exception:
            logger.exception("ai_watcher: AI call unexpected")
            return None

        content = resp.choices[0].message.content or ""
        try:
            raw = json.loads(content)
            return WatchResult.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "ai_watcher: parse failed: {} | raw[:200]={}",
                exc, content[:200].replace("\n", " "),
            )
            return None

    return asyncio.run(_call())


# ── 单个 / 全部 ────────────────────────────────────────────────────────


def watch_symbol(user_id: int, symbol: str, period: str = "1d") -> AiAlert | None:
    """对单个标的跑一次盯盘。返回落库的 AiAlert，失败返回 None。"""
    snapshot = build_snapshot(symbol, period=period)
    if snapshot is None:
        return None

    result = _call_ai_json(snapshot)
    if result is None:
        return None

    with SyncSessionLocal() as db:
        alert = AiAlert(
            user_id=user_id,
            symbol=snapshot["symbol"],
            level=result.level,
            signal=result.signal,
            reason=result.reason,
            snapshot=snapshot,
            acked=False,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id

    publish_event(
        f"ai.alert.{result.level}",
        {
            "alert_id": alert_id,
            "symbol": snapshot["symbol"],
            "signal": result.signal,
            "level": result.level,
            "close": snapshot["close"],
            "rsi14": snapshot["rsi14"],
            "ret_5d_pct": snapshot["ret_5d_pct"],
        },
        user_id=user_id,
        level=result.level if result.level in ("warn", "danger") else "info",
    )
    logger.info(
        "ai_watcher: user={} symbol={} → level={} signal={}",
        user_id, snapshot["symbol"], result.level, result.signal,
    )
    return alert


def watch_all_for_user(user_id: int) -> dict[str, int]:
    """跑该用户所有 watchlist。返回 {"ok": n, "skipped": m, "failed": k}。"""
    with SyncSessionLocal() as db:
        rows = db.execute(
            select(Watchlist).where(Watchlist.user_id == user_id)
        ).scalars().all()
        symbols = [r.symbol for r in rows]

    stats = {"ok": 0, "skipped": 0, "failed": 0}
    for sym in symbols:
        try:
            alert = watch_symbol(user_id, sym)
            if alert is None:
                stats["skipped"] += 1
            else:
                stats["ok"] += 1
        except Exception:
            logger.exception("ai_watcher: {} unexpected", sym)
            stats["failed"] += 1
    return stats
