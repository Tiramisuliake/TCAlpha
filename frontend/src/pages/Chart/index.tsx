import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  message,
} from "antd";
import {
  DownloadOutlined,
  RobotOutlined,
  StopOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createChart } from "lightweight-charts";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import { getKline, getSymbols, triggerDownload } from "@/api/market";
import { streamChartAnalysis } from "@/api/ai_chart";
import type { KlineBar, Period, QuoteUpdate } from "@/types";
import { PageScaffold } from "@/components/PageScaffold";
import { PermButton } from "@/components/PermButton";
import { useWebSocket } from "@/hooks/useWebSocket";
import { wsUrl as buildWsUrl } from "@/store/useAuthStore";

// 涨跌色（A 股惯例 红涨绿跌），与 styles/index.css 的 --tc-up/--tc-down 对齐
const UP = "#ef4444";
const DOWN = "#00a778";

const PERIODS: { label: string; value: Period }[] = [
  { label: "日K", value: "1d" },
  { label: "60分", value: "60m" },
  { label: "30分", value: "30m" },
  { label: "15分", value: "15m" },
  { label: "5分", value: "5m" },
  { label: "1分", value: "1m" },
];

function KlineChart({ bars }: { bars: KlineBar[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // 建图实例：只一次（[]）。避免每次 bars 变化销毁重建导致闪烁。
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 420,
      layout: { background: { color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#f0f0f0" }, horzLines: { color: "#f0f0f0" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#ddd" },
      rightPriceScale: { borderColor: "#ddd" },
    });
    chartRef.current = chart;

    candleRef.current = chart.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });

    volRef.current = chart.addHistogramSeries({
      color: "#94a3b8",
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const onResize = () => {
      if (!ref.current) return;
      chart.applyOptions({
        width: ref.current.clientWidth,
        height: ref.current.clientHeight,
      });
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(el);
    window.addEventListener("resize", onResize);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      window.removeEventListener("resize", onResize);
    };
  }, []);

  // 数据更新：bars 变化只 setData，不重建图。
  useEffect(() => {
    if (!candleRef.current || !volRef.current) return;
    const candleData = bars.map((b) => ({
      time: Math.floor(new Date(b.dt).getTime() / 1000) as UTCTimestamp,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    const volData = bars.map((b) => ({
      time: Math.floor(new Date(b.dt).getTime() / 1000) as UTCTimestamp,
      value: b.volume,
      color: b.close >= b.open ? `${UP}80` : `${DOWN}80`,
    }));
    candleRef.current.setData(candleData);
    volRef.current.setData(volData);
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  return <div ref={ref} className="w-full h-full min-h-[320px]" />;
}

export default function ChartPage() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [period, setPeriod] = useState<Period>("1d");
  const [symbolSearch, setSymbolSearch] = useState("");

  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiStreaming, setAiStreaming] = useState(false);
  const aiAbortRef = useRef<AbortController | null>(null);

  const [quote, setQuote] = useState<QuoteUpdate | null>(null);
  // 切换 symbol 时重置
  useEffect(() => {
    setQuote(null);
  }, [symbol]);

  const wsUrl = useMemo(() => {
    if (!symbol) return "";
    return buildWsUrl(`/ws/quote?symbol=${encodeURIComponent(symbol)}`);
  }, [symbol]);

  useWebSocket(
    wsUrl,
    (raw) => {
      try {
        const msg = JSON.parse(raw);
        if (msg && typeof msg === "object" && "price" in msg) {
          setQuote(msg as QuoteUpdate);
        }
      } catch {
        // ignore
      }
    },
    { enabled: !!symbol }
  );

  const { data: symbolsData } = useQuery({
    queryKey: ["symbols", { search: symbolSearch, limit: 50 }],
    queryFn: () => getSymbols({ search: symbolSearch || undefined, limit: 50 }),
    staleTime: 60_000,
  });

  const { data: klineData, isLoading, isFetching } = useQuery({
    queryKey: ["kline", symbol, period],
    queryFn: () => getKline(symbol!, period, 500),
    enabled: !!symbol,
    staleTime: 30_000,
  });

  const downloadMut = useMutation({
    mutationFn: () => triggerDownload(symbol!, period),
    onSuccess: (res: { task_id: string }) => {
      message.success(`下载任务已提交（task: ${res.task_id.slice(0, 8)}…），正在等待数据回填…`);
      // 下载走 Celery 异步，完成时间不定：有限次轮询自动刷新 K 线，省去手动刷新页面
      const sym = symbol;
      const prd = period;
      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        qc.invalidateQueries({ queryKey: ["kline", sym, prd] });
        if (tries >= 6) clearInterval(timer);
      }, 3000);
    },
  });

  const symbolOptions = symbolsData?.items.map((s) => ({
    value: s.symbol,
    label: `${s.code} ${s.name}`,
  })) ?? [];

  const bars = klineData?.bars ?? [];

  const runAi = async () => {
    if (!symbol) return;
    aiAbortRef.current?.abort();
    const ctrl = new AbortController();
    aiAbortRef.current = ctrl;

    setAiOpen(true);
    setAiText("");
    setAiStreaming(true);

    await streamChartAnalysis(symbol, period, {
      signal: ctrl.signal,
      onChunk: (text) => setAiText((prev) => prev + text),
      onDone: () => setAiStreaming(false),
      onError: (msg) => {
        message.error(`AI 解读失败：${msg}`);
        setAiStreaming(false);
      },
    });
  };

  const stopAi = () => {
    aiAbortRef.current?.abort();
    setAiStreaming(false);
  };

  useEffect(() => {
    return () => {
      aiAbortRef.current?.abort();
    };
  }, []);

  return (
    <PageScaffold>
      <Card
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
      >
        <Space className="flex flex-wrap gap-2 mb-4">
          <Select
            showSearch
            placeholder="输入代码或名称搜索"
            style={{ width: 200 }}
            value={symbol}
            onChange={setSymbol}
            onSearch={setSymbolSearch}
            filterOption={false}
            options={symbolOptions}
            notFoundContent={symbolSearch ? "未找到" : "请输入代码或名称"}
          />
          <Space.Compact>
            {PERIODS.map((p) => (
              <Button
                key={p.value}
                type={period === p.value ? "primary" : "default"}
                size="small"
                onClick={() => setPeriod(p.value)}
              >
                {p.label}
              </Button>
            ))}
          </Space.Compact>
          {symbol && (
            <PermButton
              perm="data.download"
              icon={<DownloadOutlined />}
              size="small"
              loading={downloadMut.isPending}
              onClick={() => downloadMut.mutate()}
            >
              下载K线
            </PermButton>
          )}
          <PermButton
            perm="ai.chat"
            type="primary"
            ghost
            icon={<RobotOutlined />}
            size="small"
            disabled={!symbol || bars.length === 0}
            onClick={runAi}
          >
            AI 解读
          </PermButton>
          {isFetching && <Spin size="small" />}
          {quote && (
            <Space className="ml-2" size={16}>
              <Statistic
                title="最新价"
                value={quote.price}
                precision={2}
                valueStyle={{
                  fontSize: 16,
                  color:
                    (quote.pct_chg ?? 0) > 0
                      ? UP
                      : (quote.pct_chg ?? 0) < 0
                        ? DOWN
                        : undefined,
                }}
              />
              {quote.pct_chg != null && (
                <Statistic
                  title="涨跌幅"
                  value={quote.pct_chg}
                  precision={2}
                  suffix="%"
                  valueStyle={{
                    fontSize: 14,
                    color: quote.pct_chg > 0 ? UP : quote.pct_chg < 0 ? DOWN : undefined,
                  }}
                />
              )}
              <Tag color="processing">实时</Tag>
            </Space>
          )}
        </Space>

        <div className="flex-1 min-h-0 flex flex-col">
          {!symbol ? (
            <div className="flex-1 flex items-center justify-center">
              <Empty description="请选择股票" />
            </div>
          ) : isLoading ? (
            <div className="flex-1 flex items-center justify-center"><Spin /></div>
          ) : bars.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <Empty description={`暂无 ${symbol} ${period} K线数据`}>
                <PermButton perm="data.download" type="primary" loading={downloadMut.isPending} onClick={() => downloadMut.mutate()}>
                  立即下载
                </PermButton>
              </Empty>
            </div>
          ) : (
            <KlineChart bars={bars} />
          )}
        </div>
      </Card>

      <Drawer
        title={
          <Space>
            <RobotOutlined />
            <span>AI 技术面解读</span>
            {symbol && <Tag color="blue">{symbol}</Tag>}
            {symbol && <Tag>{period}</Tag>}
          </Space>
        }
        placement="right"
        width={480}
        open={aiOpen}
        onClose={() => {
          stopAi();
          setAiOpen(false);
        }}
        extra={
          <Space>
            {aiStreaming ? (
              <Button size="small" icon={<StopOutlined />} onClick={stopAi}>
                停止
              </Button>
            ) : (
              <PermButton
                perm="ai.chat"
                size="small"
                icon={<ReloadOutlined />}
                onClick={runAi}
                disabled={!symbol}
              >
                重新分析
              </PermButton>
            )}
          </Space>
        }
      >
        {aiStreaming && !aiText ? (
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <Spin size="small" />
            <span>正在分析…</span>
          </div>
        ) : aiText ? (
          <div className="whitespace-pre-wrap text-sm leading-7 text-slate-800">
            {aiText}
            {aiStreaming && (
              <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-current animate-pulse" />
            )}
          </div>
        ) : (
          <div className="text-slate-400 text-sm">点击"重新分析"开始</div>
        )}
      </Drawer>
    </PageScaffold>
  );
}
