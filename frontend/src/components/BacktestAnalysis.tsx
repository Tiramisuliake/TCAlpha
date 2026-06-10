import { Card, Col, Row, Statistic } from "antd";
import ReactECharts from "echarts-for-react";
import type { BacktestResult } from "@/types";

/** 把小数收益率格式化为百分比字符串。 */
function pct(v: number | undefined | null, digits = 2): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(digits)}%`;
}

function StatCard({ label, value, suffix = "" }: { label: string; value: string | number; suffix?: string }) {
  return (
    <Card size="small" className="text-center">
      <Statistic title={label} value={value} suffix={suffix} valueStyle={{ fontSize: 16 }} />
    </Card>
  );
}

/**
 * 回测绩效深化分析：风险标量 + 月度收益热力图 + 滚动夏普/Beta + 相对强弱。
 *
 * 全部字段都是可选的（后端 result JSON 向后兼容），旧回测缺字段时对应卡片不渲染。
 */
export function BacktestAnalysis({ result }: { result: BacktestResult }) {
  const monthly = result.monthly_returns ?? [];
  const rollingSharpe = result.rolling_sharpe ?? [];
  const rollingBeta = result.rolling_beta ?? [];
  const relStrength = result.relative_strength ?? [];

  const hasMonthly = monthly.length > 0;
  const hasRolling = rollingSharpe.length > 0;
  const hasBeta = rollingBeta.length > 0;
  const hasRel = relStrength.length > 0;

  // ── 月度收益热力图：年×月网格，红涨绿跌（A 股惯例） ──
  const years = [...new Set(monthly.map((m) => m.month.slice(0, 4)))].sort();
  const heatData = monthly.map((m) => {
    const monthIdx = parseInt(m.month.slice(5, 7), 10) - 1; // 0-11
    const yearIdx = years.indexOf(m.month.slice(0, 4));
    return [monthIdx, yearIdx, Number((m.value * 100).toFixed(2))];
  });
  const maxAbs = Math.max(0.01, ...monthly.map((m) => Math.abs(m.value * 100)));
  const monthLabels = Array.from({ length: 12 }, (_, i) => `${i + 1}月`);

  const heatOption = {
    tooltip: {
      position: "top",
      formatter: (p: { value: number[] }) =>
        `${years[p.value[1]]}-${String(p.value[0] + 1).padStart(2, "0")}：${p.value[2]}%`,
    },
    grid: { left: 48, right: 16, top: 10, bottom: 56 },
    xAxis: { type: "category", data: monthLabels, splitArea: { show: true } },
    yAxis: { type: "category", data: years, splitArea: { show: true } },
    visualMap: {
      min: -maxAbs,
      max: maxAbs,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 8,
      itemHeight: 80,
      inRange: { color: ["#10b981", "#f8fafc", "#ef4444"] },
      textStyle: { fontSize: 10 },
    },
    series: [
      {
        type: "heatmap",
        data: heatData,
        label: {
          show: true,
          fontSize: 10,
          formatter: (p: { value: number[] }) => `${p.value[2]}`,
        },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.3)" } },
      },
    ],
  };

  // ── 滚动夏普 + 滚动 Beta（双 y 轴；Beta 按日期对齐到夏普的 x 轴） ──
  const rsDates = rollingSharpe.map((p) => p.dt);
  const betaByDay = new Map(rollingBeta.map((p) => [p.dt, p.value]));
  const betaAligned = rsDates.map((d) => betaByDay.get(d) ?? null);

  const rollOption = {
    tooltip: { trigger: "axis" },
    legend: {
      data: hasBeta ? ["滚动夏普", "滚动Beta"] : ["滚动夏普"],
      top: 0,
      textStyle: { fontSize: 11 },
    },
    grid: { left: 48, right: 48, top: 28, bottom: 36 },
    xAxis: { type: "category", data: rsDates, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: [
      { type: "value", name: "夏普", scale: true },
      { type: "value", name: "Beta", scale: true },
    ],
    series: [
      {
        name: "滚动夏普",
        type: "line",
        data: rollingSharpe.map((p) => p.value),
        smooth: true,
        symbol: "none",
        yAxisIndex: 0,
        lineStyle: { color: "#3b82f6", width: 1.5 },
      },
      ...(hasBeta
        ? [
            {
              name: "滚动Beta",
              type: "line",
              data: betaAligned,
              smooth: true,
              symbol: "none",
              connectNulls: true,
              yAxisIndex: 1,
              lineStyle: { color: "#f59e0b", width: 1.5 },
            },
          ]
        : []),
    ],
  };

  // ── 相对强弱：策略归一 / 基准归一（>1 跑赢基准） ──
  const relOption = {
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 16, top: 16, bottom: 36 },
    xAxis: { type: "category", data: relStrength.map((p) => p.dt), axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: { type: "value", name: "RS", scale: true },
    series: [
      {
        name: "相对强弱",
        type: "line",
        data: relStrength.map((p) => p.value),
        smooth: true,
        symbol: "none",
        lineStyle: { color: "#8b5cf6", width: 1.5 },
        areaStyle: { color: "rgba(139,92,246,0.12)" },
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 1 }],
          lineStyle: { color: "#94a3b8", type: "dashed" },
          label: { formatter: "基准=1", fontSize: 10 },
        },
      },
    ],
  };

  const ddInterval =
    result.max_dd_start && result.max_dd_end
      ? `${result.max_dd_start} → ${result.max_dd_end}（${result.max_dd_days ?? 0} 天）｜修复：${result.max_dd_recovery ?? "未修复"}`
      : "无显著回撤";

  return (
    <div className="flex flex-col gap-4">
      <Card title="风险与收益深化" size="small">
        <Row gutter={[8, 8]}>
          <Col span={8}>
            <StatCard label="Calmar 比率" value={result.calmar != null ? result.calmar.toFixed(3) : "-"} />
          </Col>
          <Col span={8}>
            <StatCard label="年化波动率" value={pct(result.volatility)} />
          </Col>
          <Col span={8}>
            <StatCard label="盈亏比" value={result.profit_factor >= 9999 ? "∞" : result.profit_factor.toFixed(2)} />
          </Col>
          <Col span={8}>
            <StatCard label="平均盈利" value={result.avg_win != null ? result.avg_win.toFixed(0) : "-"} />
          </Col>
          <Col span={8}>
            <StatCard label="平均亏损" value={result.avg_loss != null ? result.avg_loss.toFixed(0) : "-"} />
          </Col>
          <Col span={8}>
            <StatCard
              label="最长连胜 / 连亏"
              value={`${result.max_win_streak ?? 0} / ${result.max_lose_streak ?? 0}`}
            />
          </Col>
        </Row>
        <div className="mt-3 text-xs text-slate-500">
          最大回撤区间：{ddInterval}
        </div>
      </Card>

      {hasMonthly && (
        <Card title="月度收益热力图" size="small">
          <ReactECharts option={heatOption} style={{ height: Math.max(160, years.length * 48 + 96) }} notMerge />
        </Card>
      )}

      {hasRolling && (
        <Card title={hasBeta ? "滚动夏普 + 滚动 Beta（60 日窗口）" : "滚动夏普（60 日窗口）"} size="small">
          <ReactECharts option={rollOption} style={{ height: 260 }} notMerge />
        </Card>
      )}

      {hasRel && (
        <Card title="相对强弱（策略 / 基准）" size="small">
          <ReactECharts option={relOption} style={{ height: 240 }} notMerge />
        </Card>
      )}
    </div>
  );
}
