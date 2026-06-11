import ReactECharts from "echarts-for-react";
import type { BacktestResult, BacktestTrade, EquityPoint } from "@/types";

function computeDrawdown(curve: EquityPoint[]): number[] {
  const dd: number[] = [];
  let peak = -Infinity;
  for (const p of curve) {
    if (p.value > peak) peak = p.value;
    dd.push(peak > 0 ? (p.value / peak - 1) * 100 : 0); // 百分比，负数
  }
  return dd;
}

function buildTradeMarkers(
  trades: BacktestTrade[],
  curve: EquityPoint[]
): Array<{ name: string; coord: [string, number]; itemStyle: { color: string }; symbol: string; symbolSize: number }> {
  if (!trades.length || !curve.length) return [];
  // 把 dt 截到日期粒度（YYYY-MM-DD）方便对齐
  const dayOf = (s: string) => s.slice(0, 10);
  const equityByDay = new Map<string, number>();
  for (const p of curve) equityByDay.set(dayOf(p.dt), p.value);

  return trades
    .map((t) => {
      const day = dayOf(t.dt);
      const v = equityByDay.get(day);
      if (v == null) return null;
      const isBuy = t.offset === "open" ? t.direction === "long" : t.direction === "short";
      return {
        name: isBuy ? "买" : "卖",
        coord: [day, v] as [string, number],
        itemStyle: { color: isBuy ? "#ef4444" : "#10b981" },
        symbol: isBuy ? "triangle" : "pin",
        symbolSize: 10,
      };
    })
    .filter((m): m is NonNullable<typeof m> => m !== null);
}

/** 资金曲线 + 回撤双区图（可叠加基准虚线与买卖标记），单标的与轮动回测共用。 */
export function EquityChart({
  result,
  trades,
}: {
  result: BacktestResult;
  trades: BacktestTrade[];
}) {
  const dates = result.equity_curve.map((p) => p.dt.slice(0, 10));
  const values = result.equity_curve.map((p) => p.value);
  const drawdown = computeDrawdown(result.equity_curve);
  const markers = buildTradeMarkers(trades, result.equity_curve);

  // 基准（指数）：按主曲线日期对齐，无数据则不画
  const benchCurve = result.benchmark_curve ?? [];
  const hasBench = benchCurve.length > 0;
  const benchByDay = new Map(benchCurve.map((p) => [p.dt.slice(0, 10), p.value]));
  const benchValues = dates.map((d) => benchByDay.get(d) ?? null);
  const benchName = result.benchmark ?? "沪深300";

  const option = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
    },
    legend: {
      data: hasBench ? ["资金曲线", benchName, "回撤"] : ["资金曲线", "回撤"],
      top: 0,
      textStyle: { fontSize: 11 },
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 60, right: 20, top: 30, height: "55%" },
      { left: 60, right: 20, top: "72%", height: "20%" },
    ],
    xAxis: [
      {
        type: "category",
        data: dates,
        gridIndex: 0,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: "category",
        data: dates,
        gridIndex: 1,
        axisLabel: { rotate: 30, fontSize: 10 },
      },
    ],
    yAxis: [
      { type: "value", name: "资金", scale: true, gridIndex: 0 },
      {
        type: "value",
        name: "回撤%",
        max: 0,
        axisLabel: { formatter: "{value}%", fontSize: 10 },
        gridIndex: 1,
      },
    ],
    series: [
      {
        name: "资金曲线",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: values,
        smooth: true,
        lineStyle: { color: "#3b82f6", width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(59,130,246,0.3)" },
              { offset: 1, color: "rgba(59,130,246,0)" },
            ],
          },
        },
        symbol: "none",
        markPoint: {
          data: markers,
          label: { show: false },
          symbolKeepAspect: true,
        },
      },
      ...(hasBench
        ? [{
            name: benchName,
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: benchValues,
            smooth: true,
            symbol: "none",
            connectNulls: true,
            lineStyle: { color: "#94a3b8", width: 1.5, type: "dashed" },
          }]
        : []),
      {
        name: "回撤",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: drawdown,
        lineStyle: { color: "#ef4444", width: 1 },
        areaStyle: { color: "rgba(239,68,68,0.25)" },
        symbol: "none",
        smooth: true,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 340 }} notMerge />;
}
