/**
 * 图表 AI 分析流式调用（Phase 5 Step 4）。
 *
 * 协议同 /api/ai/chat：data <chunk-json> 增量、data [DONE] 结束、data [ERROR]xxx 异常。
 * 不同点：这里是 GET（参数走 query），可以走原生 EventSource，但为了和 streamChat
 * 共用 abort / 错误处理逻辑，统一用 fetch + ReadableStream。
 */
import { authHeader } from "@/store/useAuthStore";

export interface ChartStreamCallbacks {
  onChunk: (text: string) => void;
  onDone?: () => void;
  onError?: (msg: string) => void;
  signal?: AbortSignal;
}

const DONE = "[DONE]";
const ERROR_PREFIX = "[ERROR]";

export async function streamChartAnalysis(
  symbol: string,
  period: string,
  cb: ChartStreamCallbacks,
): Promise<void> {
  const qs = new URLSearchParams({ symbol, period });
  const resp = await fetch(`/api/ai/chart/analyze?${qs.toString()}`, {
    method: "GET",
    headers: { Accept: "text/event-stream", ...authHeader() },
    signal: cb.signal,
  });

  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => resp.statusText);
    cb.onError?.(`HTTP ${resp.status}: ${text}`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trimStart();
          if (data === DONE) {
            cb.onDone?.();
            return;
          }
          if (data.startsWith(ERROR_PREFIX)) {
            cb.onError?.(data.slice(ERROR_PREFIX.length));
            return;
          }
          try {
            const text = JSON.parse(data) as string;
            cb.onChunk(text);
          } catch {
            cb.onChunk(data);
          }
        }
      }
    }
    cb.onDone?.();
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    cb.onError?.((e as Error).message || "stream failed");
  }
}
