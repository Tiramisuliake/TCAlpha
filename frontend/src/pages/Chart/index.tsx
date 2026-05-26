import { useEffect, useRef, useState } from "react";
import { Button, Card, Empty, Select, Space, Spin, message } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useQuery, useMutation } from "@tanstack/react-query";
import { createChart } from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";
import { getKline, getSymbols, triggerDownload } from "@/api/market";
import type { KlineBar, Period } from "@/types";

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

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 420,
      layout: { background: { color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#f0f0f0" }, horzLines: { color: "#f0f0f0" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#ddd" },
      rightPriceScale: { borderColor: "#ddd" },
    });
    chartRef.current = chart;

    const candle = chart.addCandlestickSeries({
      upColor: "#ef4444",
      downColor: "#10b981",
      borderUpColor: "#ef4444",
      borderDownColor: "#10b981",
      wickUpColor: "#ef4444",
      wickDownColor: "#10b981",
    });

    const vol = chart.addHistogramSeries({
      color: "#94a3b8",
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const candleData = bars.map((b) => ({
      time: Math.floor(new Date(b.dt).getTime() / 1000) as unknown as number,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    const volData = bars.map((b) => ({
      time: Math.floor(new Date(b.dt).getTime() / 1000) as unknown as number,
      value: b.volume,
      color: b.close >= b.open ? "#ef444480" : "#10b98180",
    }));

    candle.setData(candleData as never);
    vol.setData(volData as never);
    chart.timeScale().fitContent();

    const onResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    window.addEventListener("resize", onResize);
    return () => {
      chart.remove();
      chartRef.current = null;
      window.removeEventListener("resize", onResize);
    };
  }, [bars]);

  return <div ref={ref} className="w-full" />;
}

export default function ChartPage() {
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [period, setPeriod] = useState<Period>("1d");
  const [symbolSearch, setSymbolSearch] = useState("");

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
      message.success(`下载任务已提交（task: ${res.task_id.slice(0, 8)}…），完成后刷新页面查看`);
    },
  });

  const symbolOptions = symbolsData?.items.map((s) => ({
    value: s.symbol,
    label: `${s.code} ${s.name}`,
  })) ?? [];

  const bars = klineData?.bars ?? [];

  return (
    <div className="space-y-4">
      <Card>
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
            <Button
              icon={<DownloadOutlined />}
              size="small"
              loading={downloadMut.isPending}
              onClick={() => downloadMut.mutate()}
            >
              下载K线
            </Button>
          )}
          {isFetching && <Spin size="small" />}
        </Space>

        {!symbol ? (
          <Empty description="请选择股票" className="py-16" />
        ) : isLoading ? (
          <div className="flex justify-center py-16"><Spin /></div>
        ) : bars.length === 0 ? (
          <Empty
            description={`暂无 ${symbol} ${period} K线数据`}
            className="py-16"
          >
            <Button type="primary" loading={downloadMut.isPending} onClick={() => downloadMut.mutate()}>
              立即下载
            </Button>
          </Empty>
        ) : (
          <KlineChart bars={bars} />
        )}
      </Card>
    </div>
  );
}
