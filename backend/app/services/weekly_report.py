"""AI 投研周报：账户净值周复盘 + 市场情绪周走势 + AI 综述，自包含 HTML。

数据聚合走同步（SyncSessionLocal + sync redis，api 层 to_thread / beat 直调）；
AI 综述为可选增强——无 key / 调用失败时降级为空段落，周报仍完整可用。
"""
from __future__ import annotations

import json
from datetime import timedelta
from html import escape

from loguru import logger

from app.utils.trading_period import now_cn


def collect_weekly_sync(user_id: int) -> dict:
    """聚合最近一周数据：账户净值（SimEquitySnapshot）+ 市场情绪温度（Redis 历史）。"""
    import redis as sync_redis
    from sqlalchemy import select

    from app.config import settings
    from app.db.models.account import SimEquitySnapshot
    from app.db.postgres import SyncSessionLocal
    from app.services.market_sentiment import _SENTIMENT_HIST_KEY

    today = now_cn().date()
    week_ago = today - timedelta(days=7)

    equity_points: list[dict] = []
    try:
        with SyncSessionLocal() as db:
            rows = db.execute(
                select(SimEquitySnapshot)
                .where(SimEquitySnapshot.user_id == user_id, SimEquitySnapshot.dt >= week_ago)
                .order_by(SimEquitySnapshot.dt)
            ).scalars().all()
        equity_points = [
            {"dt": str(r.dt), "total_asset": round(r.total_asset, 2)} for r in rows
        ]
    except Exception as exc:
        logger.warning("weekly_report equity query failed: {}", exc)

    equity = {"points": equity_points, "start": 0.0, "end": 0.0, "change_pct": 0.0}
    if equity_points:
        start, end = equity_points[0]["total_asset"], equity_points[-1]["total_asset"]
        equity.update(
            start=start, end=end,
            change_pct=round((end / start - 1) * 100, 2) if start > 0 else 0.0,
        )

    sentiment: list[dict] = []
    try:
        r = sync_redis.from_url(settings.redis_url, decode_responses=True)
        try:
            raw = r.hgetall(_SENTIMENT_HIST_KEY)
        finally:
            r.close()
        points = sorted((json.loads(v) for v in raw.values()), key=lambda p: p.get("date", ""))
        sentiment = [
            {"date": p["date"], "temperature": p.get("temperature", 50),
             "limit_up": p.get("limit_up", 0)}
            for p in points if p.get("date", "") >= str(week_ago)
        ]
    except Exception as exc:
        logger.warning("weekly_report sentiment read failed: {}", exc)

    return {
        "week_start": str(week_ago),
        "week_end": str(today),
        "equity": equity,
        "sentiment": sentiment,
    }


async def ai_weekly_summary(data: dict) -> str:
    """AI 综述段落（可选增强）：失败 / 无 key 时返回空串降级。"""
    try:
        from app.schemas.ai import ChatMessage
        from app.services.ai import stream_chat

        eq = data["equity"]
        temps = [p["temperature"] for p in data["sentiment"]]
        prompt = (
            f"请以 A 股投研助理身份写一段不超过 150 字的中文周度综述。数据：\n"
            f"- 模拟账户净值 {eq['start']} → {eq['end']}（{eq['change_pct']:+.2f}%）\n"
            f"- 市场情绪温度序列（0-100）：{temps or '暂无'}\n"
            f"要求：客观、指出风险、不构成投资建议。"
        )
        chunks = [c async for c in stream_chat([ChatMessage(role="user", content=prompt)])]
        return "".join(chunks).strip()
    except Exception as exc:
        logger.warning("weekly_report ai summary degraded: {}", exc)
        return ""


def build_weekly_html(data: dict, ai_text: str = "") -> str:
    """渲染自包含 HTML 周报（零外部依赖，离线可看）。"""
    eq = data["equity"]
    chg = eq["change_pct"]
    chg_cls = "up" if chg >= 0 else "down"

    senti_rows = "".join(
        f'<tr><td>{escape(p["date"])}</td><td>{p["temperature"]}</td><td>{p["limit_up"]}</td></tr>'
        for p in data["sentiment"]
    ) or '<tr><td colspan="3">（暂无情绪存档）</td></tr>'

    eq_rows = "".join(
        f'<tr><td>{escape(p["dt"])}</td><td>{p["total_asset"]:,.2f}</td></tr>'
        for p in eq["points"]
    ) or '<tr><td colspan="2">（本周无净值快照）</td></tr>'

    ai_block = (
        f'<h2>AI 综述</h2><p>{escape(ai_text)}</p>' if ai_text
        else '<h2>AI 综述</h2><p class="muted">（AI 服务不可用，本期无综述）</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>TCAlpha 投研周报 {escape(data["week_end"])}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 860px;
         margin: 24px auto; padding: 0 16px; color: #1e293b; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 16px; margin-top: 24px; }}
  .muted {{ color: #64748b; font-size: 12px; }}
  .big {{ font-size: 26px; font-weight: 700; }}
  table {{ border-collapse: collapse; font-size: 12px; width: 100%; }}
  th, td {{ border: 1px solid #e2e8f0; padding: 4px 10px; text-align: right; }}
  th {{ background: #f8fafc; }}
  .up {{ color: #ef4444; }} .down {{ color: #10b981; }}
</style></head><body>
<h1>TCAlpha 投研周报</h1>
<p class="muted">区间 {escape(data["week_start"])} ~ {escape(data["week_end"])}
 ｜ 生成于 {now_cn().strftime("%Y-%m-%d %H:%M")}</p>
<h2>账户净值周复盘</h2>
<p class="big {chg_cls}">{chg:+.2f}%</p>
<p class="muted">期初 {eq["start"]:,.2f} → 期末 {eq["end"]:,.2f}</p>
<table><tr><th>日期</th><th>总资产</th></tr>{eq_rows}</table>
<h2>市场情绪周走势</h2>
<table><tr><th>日期</th><th>温度</th><th>涨停家数</th></tr>{senti_rows}</table>
{ai_block}
<p class="muted">本报告由 TCAlpha 自动生成，仅供研究复盘，不构成投资建议。</p>
</body></html>"""
