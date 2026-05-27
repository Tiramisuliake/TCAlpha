"""图表 AI 分析（Phase 5 Step 4）。

复用 ai_watcher.build_snapshot 拿技术指标快照，喂给 LLM 做流式自然语言解读，
通过 SSE 推送到前端。和 ai_watcher 的区别：watcher 是严格 JSON、用于落库 +
告警；这里是给人看的 markdown 文本、流式输出。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.schemas.ai import ChatMessage
from app.services.ai import stream_chat
from app.services.ai_watcher import build_snapshot
from app.utils.symbol import normalize

_SYSTEM_PROMPT = (
    "你是 TCAlpha A 股技术分析师。仅基于用户给的指标快照做客观判断，"
    "输出简洁的中文 markdown。要求：\n"
    "- 分四段：**趋势** / **支撑压力** / **短期信号** / **风险点**\n"
    "- 每段一两句话，控制在 60 字以内\n"
    "- 不要推测未来价格；只描述已有指标含义\n"
    "- 不要出现'建议买入/卖出'等可被视为投资建议的语句，改用'短线偏强 / 谨慎'\n"
    "- 末尾加一行小字：*仅供学习参考，不构成投资建议*"
)


async def analyze_chart(symbol: str, period: str = "1d") -> AsyncIterator[str]:
    """流式生成 K 线技术面解读。

    - period 目前仅 build_snapshot 支持的日线（bar_1d）；保留参数以便后续扩展。
    - snapshot 为 None 时 yield 一条友好提示并结束。
    """
    sym = normalize(symbol)
    snapshot = build_snapshot(sym)
    if snapshot is None:
        yield (
            f"⚠️ {sym} 暂无足够日 K 数据（需 ≥ 25 根）。"
            f"请先到「数据管理」下载该股票的日 K 数据。"
        )
        return

    user_prompt = (
        f"以下是 **{sym}** 最近 60 个交易日的技术指标快照，请按系统提示给解读：\n\n"
        f"- 截至：{snapshot['as_of']}\n"
        f"- 最新收盘：{snapshot['close']}\n"
        f"- 最近 5 日收盘：{snapshot['recent_close_5d']}\n"
        f"- MA5 / MA10 / MA20：{snapshot['ma5']} / {snapshot['ma10']} / {snapshot['ma20']}\n"
        f"- RSI(14)：{snapshot['rsi14']}\n"
        f"- MACD：dif={snapshot['macd_dif']}  dea={snapshot['macd_dea']}  hist={snapshot['macd_hist']}\n"
        f"- 近 5 日 / 20 日涨跌幅：{snapshot['ret_5d_pct']}% / {snapshot['ret_20d_pct']}%\n"
        f"- 最新成交量 / 5 日均量：{snapshot['vol_last']} / {snapshot['vol_avg_5d']}\n"
        f"\n周期：{period}"
    )

    async for chunk in stream_chat(
        [ChatMessage(role="user", content=user_prompt)],
        system=_SYSTEM_PROMPT,
        temperature=0.4,
    ):
        yield chunk
