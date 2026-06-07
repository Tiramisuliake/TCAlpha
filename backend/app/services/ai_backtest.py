"""回测 AI 归因（④）：取回测绩效指标喂 LLM，流式输出归因解读。

仿 ai_chart：拼 prompt → stream_chat → SSE。区别是数据来自 PG 回测 result。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai import ChatMessage
from app.services import backtest as backtest_svc
from app.services.ai import stream_chat

_SYSTEM_PROMPT = (
    "你是 TCAlpha 量化策略分析师。基于用户给的回测绩效指标做客观归因，"
    "输出简洁的中文 markdown。要求：\n"
    "- 分四段：**整体表现** / **风险特征** / **可能原因** / **优化方向**\n"
    "- 每段两三句话，结合收益、回撤、夏普、胜率、盈亏比综合判断\n"
    "- 不臆测未来收益，只解读已有指标\n"
    "- 末尾加一行小字：*仅供学习参考，不构成投资建议*"
)


def _pct(x: object) -> str:
    return f"{x * 100:.2f}%" if isinstance(x, (int, float)) else "-"


def _num(x: object) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


async def analyze_backtest(
    db: AsyncSession, job_id: int, user_id: int
) -> AsyncIterator[str]:
    """流式生成某个回测任务的绩效归因。

    - job 不存在/非本人 → 友好提示
    - 未完成或无 result → 友好提示
    """
    job = await backtest_svc.get_backtest_status(db, job_id, user_id)
    if job is None:
        yield f"⚠️ 未找到回测任务 #{job_id}（或无权访问）。"
        return
    if job.status != "done" or not job.result:
        yield f"⚠️ 回测 #{job_id} 尚未完成（当前状态：{job.status}），暂无法归因。"
        return

    m = job.result
    user_prompt = (
        f"以下是策略回测 **#{job_id}** 的绩效指标，请按系统提示归因：\n\n"
        f"- 总收益率：{_pct(m.get('total_return'))}\n"
        f"- 最大回撤：{_pct(m.get('max_drawdown'))}\n"
        f"- 夏普比率：{_num(m.get('sharpe'))}\n"
        f"- 交易笔数：{m.get('trade_count', '-')}\n"
        f"- 胜率：{_pct(m.get('win_rate'))}\n"
        f"- 盈亏比：{_num(m.get('profit_factor'))}\n"
    )

    async for chunk in stream_chat(
        [ChatMessage(role="user", content=user_prompt)],
        system=_SYSTEM_PROMPT,
        temperature=0.4,
    ):
        yield chunk
