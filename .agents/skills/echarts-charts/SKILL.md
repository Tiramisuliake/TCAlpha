---
name: echarts-charts
description: ECharts 通用图表 + lightweight-charts 高性能 K 线 / 指标叠加 / 交易标记。触发词：ECharts、lightweight-charts、K 线、candlestick、图表、chart、指标、技术指标、收益曲线
---

# 图表

## 选型分工

| 用途 | 库 |
|---|---|
| K 线主图（高性能、tick 增量） | `lightweight-charts` |
| 收益曲线 / 回撤 / 双轴 / 复杂统计 | `echarts` |
| 简单柱状 / 饼图 | `echarts` |

K 线用 lightweight 是因为 ECharts 大数据点卡，lightweight 是 TradingView 出品。

## lightweight-charts K 线模板

```tsx
import { createChart, CandlestickSeries, HistogramSeries } from "lightweight-charts";
import { useEffect, useRef } from "react";

export function Kline({ bars }: { bars: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 480,
      layout: { background: { color: "#fff" }, textColor: "#333" },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444", downColor: "#10b981",     // A 股涨红跌绿
      borderUpColor: "#ef4444", borderDownColor: "#10b981",
      wickUpColor: "#ef4444", wickDownColor: "#10b981",
    });
    candle.setData(bars.map((b) => ({
      time: (new Date(b.dt).getTime() / 1000) as any,
      open: b.open, high: b.high, low: b.low, close: b.close,
    })));

    const vol = chart.addSeries(HistogramSeries, {
      color: "#94a3b8",
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    vol.setData(bars.map((b) => ({
      time: (new Date(b.dt).getTime() / 1000) as any,
      value: b.volume,
      color: b.close >= b.open ? "#ef4444" : "#10b981",
    })));

    const resize = () => chart.applyOptions({ width: ref.current!.clientWidth });
    window.addEventListener("resize", resize);
    return () => { chart.remove(); window.removeEventListener("resize", resize); };
  }, [bars]);

  return <div ref={ref} className="w-full" />;
}
```

## 增量更新（实时行情）

```tsx
const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
// 收到 WS tick
candleRef.current?.update({ time, open, high, low, close });
```

## ECharts 收益曲线

```tsx
import ReactECharts from "echarts-for-react";

const option = {
  tooltip: { trigger: "axis" },
  legend: { data: ["净值", "回撤"] },
  xAxis: { type: "category", data: dates },
  yAxis: [
    { type: "value", name: "净值" },
    { type: "value", name: "回撤", position: "right", inverse: true, max: 0 },
  ],
  series: [
    { name: "净值", type: "line", data: equity, yAxisIndex: 0 },
    { name: "回撤", type: "line", areaStyle: {}, data: drawdown, yAxisIndex: 1, color: "#ef4444" },
  ],
};

<ReactECharts option={option} style={{ height: 360 }} />
```

## 大数据点优化

ECharts:
```ts
series: [{
  type: "line",
  large: true,
  largeThreshold: 2000,
  sampling: "lttb",
  progressive: 1000,
  data: hugeArray,
}]
```

lightweight-charts 没限制（设计目标就是百万级 K 线）。

## 指标叠加（MA / MACD）

主图叠 MA：用 `chart.addSeries(LineSeries, ...)` 加 series。
副图（MACD / RSI）：建议**第二个 chart 实例** 用 `syncCrosshair`（lightweight v4+）联动。

## 主题适配

主题切换时 `chart.applyOptions({ layout: { background, textColor } })`。
不要重建 chart（性能差）。

## 禁止

- ❌ 把万级 K 线塞 ECharts candlestick
- ❌ 每次 props 变化重建 chart 实例（用 ref + update）
- ❌ 忘了清理（`chart.remove()` 在 effect cleanup）
- ❌ 在 SSR 环境直接 import lightweight-charts（本项目纯 SPA，不影响）
