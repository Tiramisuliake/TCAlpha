---
name: ai-services
description: AI 服务集成（OpenAI 兼容 API）/ 流式输出 / 多模型切换 / 图表 AI 分析。触发词：AI、OpenAI、Claude、DeepSeek、GLM、智谱、流式、stream、chat、AI 分析、SSE、prompt
---

# AI 服务

## 协议：OpenAI 兼容

所有模型走 OpenAI Chat Completions 兼容协议（含 DeepSeek、智谱 GLM、Moonshot 等）。
配置在 `app/config.py` 的 `ai_api_base / ai_api_key / ai_model`。

## 客户端封装

```python
# app/services/ai.py
from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.ai_api_key, base_url=settings.ai_api_base)
    return _client

async def stream(message: str, system: str | None = None):
    """流式生成（异步生成器）。"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": message})

    resp = await get_client().chat.completions.create(
        model=settings.ai_model,
        messages=msgs,
        stream=True,
        temperature=0.7,
    )
    async for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

## 端点（SSE）

```python
@router.get("/chat")
async def chat(message: str):
    async def gen():
        async for chunk in ai_svc.stream(message):
            yield {"data": chunk}
        yield {"data": "[DONE]"}
    return EventSourceResponse(gen())
```

## 多模型切换

后期支持多模型时把配置改成字典：

```python
# .env
AI_MODELS={"deepseek": {"base":"...", "key":"...", "model":"deepseek-chat"}, "glm": {...}}
DEFAULT_AI_MODEL=deepseek
```

`get_client(name)` 按名取配置。

## 图表 AI 分析（Phase 5）

把当前图表的指标快照 + 行情数据 → 拼成 prompt → 让 AI 给分析。

```python
async def analyze_chart(symbol: str, period: str, kline_summary: dict) -> AsyncIterator[str]:
    system = """你是一名 A 股技术分析师。请基于以下数据给出客观分析与操作建议（仅供学习）。"""
    user = f"""
股票：{symbol}
周期：{period}
最近 20 根 K 线收盘：{kline_summary['recent_close']}
MACD：dif={kline_summary['macd_dif']:.2f}, dea={kline_summary['macd_dea']:.2f}
RSI(14)：{kline_summary['rsi']:.1f}
MA(5/10/20)：{kline_summary['ma5']:.2f}/{kline_summary['ma10']:.2f}/{kline_summary['ma20']:.2f}

请从以下维度分析（每点 1-2 句话）：
1. 趋势方向
2. 关键支撑/压力
3. 短期信号
4. 风险点
""".strip()
    async for chunk in stream(user, system=system):
        yield chunk
```

## Prompt 工程

- 用 `system` 限定角色和输出格式（"中文"、"不超过 200 字"、"列出 3 点"）
- 把数据用 markdown 表格 / json 喂给模型（结构化）
- 控制输入长度（K 线 > 200 根直接 sample 或 summarize）

## 限流与降级

- AI API 也会限流（429）→ 重试 + 退避
- 用户级配额：Redis `ai:quota:user:{uid}` 每天扣减
- 失败时给前端友好兜底：`"AI 服务暂不可用，请稍后再试"`

## 前端 SSE 接入

```ts
useSSE(`/api/ai/chat?message=${encodeURIComponent(msg)}`, (chunk) => {
  if (chunk === "[DONE]") setStreaming(false);
  else setResponse((prev) => prev + chunk);
});
```

## 测试

mock OpenAI 客户端：

```python
@patch("app.services.ai.get_client")
async def test_stream(mock_get_client):
    mock_get_client.return_value.chat.completions.create = AsyncMock(
        return_value=fake_stream(["hello ", "world"])
    )
    out = [c async for c in ai_svc.stream("hi")]
    assert "".join(out) == "hello world"
```

## 安全

- API Key 永远走 `.env`，禁止硬编码 / commit
- 用户 prompt 经过简单注入检查（禁止 `<script>` 注入）
- AI 输出做 markdown 渲染前 escape HTML
- 不要把用户的 K 线数据无脑发给第三方（明确告知用户 / 隐私协议）

## 禁止

- ❌ 前端直接调 OpenAI（必须走后端）
- ❌ AI 任务长跑放 endpoint（用 Celery 或 SSE，不阻塞）
- ❌ 把生产 key 写 `docker-compose.yml`
- ❌ AI 输出当真实操作建议直接执行下单（必须人工确认）
