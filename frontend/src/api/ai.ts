/**
 * AI 流式调用（SSE over fetch）。
 *
 * 协议参见 backend/app/api/ai.py：
 *   data: "<chunk-json-string>"
 *   data: [DONE]
 *   data: [ERROR]<msg>
 */
import { fetchWithAuthRefresh, streamHeaders } from "@/api/streamClient";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  system?: string;
  temperature?: number;
}

export interface StreamCallbacks {
  onChunk: (text: string) => void;
  onDone?: () => void;
  onError?: (msg: string) => void;
  signal?: AbortSignal;
}

const DONE = "[DONE]";
const ERROR_PREFIX = "[ERROR]";

/** 消费 SSE 响应流，按帧解析 data: 行并回调（chat / 回测归因共用）。 */
async function consumeSSE(resp: Response, cb: StreamCallbacks): Promise<void> {
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

      // SSE 帧以 "\n\n" 分隔
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
          // 服务端把 chunk JSON.dumps 过，这里反序列化（兼容裸字符串）
          try {
            cb.onChunk(JSON.parse(data) as string);
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

/** 流式 chat（POST，因为浏览器 EventSource 只支持 GET）。 */
export async function streamChat(req: ChatRequest, cb: StreamCallbacks): Promise<void> {
  const resp = await fetchWithAuthRefresh("/api/ai/chat", () => ({
    method: "POST",
    headers: streamHeaders({
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    }),
    body: JSON.stringify(req),
    signal: cb.signal,
  }));
  await consumeSSE(resp, cb);
}

/** 流式回测绩效归因（GET /api/ai/backtest/{jobId}/analyze）。 */
export async function streamBacktestAnalysis(
  jobId: number,
  cb: StreamCallbacks,
): Promise<void> {
  const resp = await fetchWithAuthRefresh(`/api/ai/backtest/${jobId}/analyze`, () => ({
    method: "GET",
    headers: streamHeaders({ Accept: "text/event-stream" }),
    signal: cb.signal,
  }));
  await consumeSSE(resp, cb);
}
