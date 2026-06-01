/**
 * AI chat 流式调用（SSE over fetch POST，无法用浏览器 EventSource，因为它只支持 GET）。
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

        // 单帧可能有多行；只关心 data:
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
          // 服务端把 chunk JSON.dumps 过，这里反序列化
          try {
            const text = JSON.parse(data) as string;
            cb.onChunk(text);
          } catch {
            // 兼容：少数情况下 chunk 是裸字符串
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
