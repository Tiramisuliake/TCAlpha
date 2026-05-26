import { useEffect, useRef } from "react";

interface UseWebSocketOptions {
  reconnectMs?: number;
  enabled?: boolean;
}

export function useWebSocket(
  url: string,
  onMessage: (data: string) => void,
  opts: UseWebSocketOptions = {}
) {
  const { reconnectMs = 3000, enabled = true } = opts;
  const wsRef = useRef<WebSocket | null>(null);
  const closedRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    closedRef.current = false;

    const connect = () => {
      if (closedRef.current) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        const parsed = (() => {
          try {
            return JSON.parse(e.data);
          } catch {
            return null;
          }
        })();
        if (parsed?.type === "ping") return;
        onMessageRef.current(e.data);
      };

      ws.onclose = () => {
        if (!closedRef.current) {
          setTimeout(connect, reconnectMs);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      closedRef.current = true;
      wsRef.current?.close();
    };
  }, [url, enabled, reconnectMs]);

  return wsRef;
}
