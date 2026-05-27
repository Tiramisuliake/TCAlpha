import { useEffect, useRef, useState } from "react";
import { Button, Input, Tooltip, message } from "antd";
import {
  ClearOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { streamChat, type ChatMessage } from "@/api/ai";

const { TextArea } = Input;

interface UIMessage extends ChatMessage {
  id: number;
  streaming?: boolean;
}

export default function Chat() {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const send = async () => {
    const text = draft.trim();
    if (!text || streaming) return;

    const userMsg: UIMessage = { id: Date.now(), role: "user", content: text };
    const assistantMsg: UIMessage = {
      id: Date.now() + 1,
      role: "assistant",
      content: "",
      streaming: true,
    };
    const nextMessages = [...messages, userMsg, assistantMsg];
    setMessages(nextMessages);
    setDraft("");
    setStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    await streamChat(
      {
        messages: nextMessages
          .filter((m) => !m.streaming)
          .map(({ role, content }) => ({ role, content })),
      },
      {
        signal: ctrl.signal,
        onChunk: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, content: m.content + chunk } : m,
            ),
          );
        },
        onDone: () => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, streaming: false } : m,
            ),
          );
          setStreaming(false);
        },
        onError: (msg) => {
          message.error(`AI 调用失败：${msg}`);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content || `⚠️ ${msg}`, streaming: false }
                : m,
            ),
          );
          setStreaming(false);
        },
      },
    );
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    setMessages((prev) => prev.map((m) => ({ ...m, streaming: false })));
  };

  const clear = () => {
    if (streaming) stop();
    setMessages([]);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex-1 flex flex-col gap-3 min-h-0">
      <div className="flex justify-end">
        <Tooltip title="清空对话">
          <Button
            icon={<ClearOutlined />}
            onClick={clear}
            disabled={messages.length === 0}
          />
        </Tooltip>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto pr-1 space-y-3 min-h-0"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400">
            <RobotOutlined className="text-4xl mb-3" />
            <p className="text-base text-slate-700 font-medium mb-1">
              问我点什么吧
            </p>
            <p className="text-sm">
              例如：现在 A 股大盘怎么看？双均线策略适合什么行情？
            </p>
          </div>
        ) : (
          messages.map((m) => <Bubble key={m.id} msg={m} />)
        )}
      </div>

      <div className="border-t border-slate-200 pt-3 flex flex-col gap-2">
        <TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled={streaming}
        />
        <div className="flex justify-end gap-2">
          {streaming && (
            <Button icon={<StopOutlined />} onClick={stop}>
              停止
            </Button>
          )}
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={send}
            disabled={streaming || !draft.trim()}
          >
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: UIMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white ${
          isUser ? "bg-blue-500" : "bg-slate-600"
        }`}
      >
        {isUser ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg whitespace-pre-wrap break-words text-sm leading-6 ${
          isUser
            ? "bg-blue-500 text-white rounded-tr-sm"
            : "bg-slate-100 text-slate-800 rounded-tl-sm"
        }`}
      >
        {msg.content || (msg.streaming ? "正在思考…" : "")}
        {msg.streaming && msg.content && (
          <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-current animate-pulse" />
        )}
      </div>
    </div>
  );
}
