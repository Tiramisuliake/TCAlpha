import { Card, Col, Row, Statistic } from "antd";
import ReactECharts from "echarts-for-react";
import type { BacktestResult, RoundTrip } from "@/types";

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

/** 把回合收益率（%）分箱成直方图数据：箱数 ~ sqrt(N)，限 5-15。 */
function buildHistogram(rets: number[]): { labels: string[]; counts: number[]; mids: number[] } {
  const min = Math.min(...rets);
  const max = Math.max(...rets);
  const binCount = Math.min(15, Math.max(5, Math.ceil(Math.sqrt(rets.length))));
  const width = (max - min) / binCount || 1;

  const counts = new Array<number>(binCount).fill(0);
  for (const r of rets) {
    const idx = Math.min(binCount - 1, Math.floor((r - min) / width));
    counts[idx] += 1;
  }
  const labels: string[] = [];
  const mids: number[] = [];
  for (let i = 0; i < binCount; i++) {
    const lo = min + i * width;
    const hi = lo + width;
    labels.push(`${lo.toFixed(1)}~${hi.toFixed(1)}`);
    mids.push((lo + hi) / 2);
  }
  return { labels, counts, mids };
}

/**
 * 交易行为分析（v0.8.3）：单笔期望 / 持仓周期 / MAE/MFE 指标卡
 * + 单笔收益率分布直方图 + 持仓周期 × 收益散点。
 *
 * 字段全部可选（旧回测结果无 round_trips 时整组不渲染）。
 */
export function TradeAnalysis({ result }: { result: BacktestResult }) {
  const trips = result.round_trips ?? [];
  if (trips.length === 0) return null;

  const rets = trips
    .filter((t): t is RoundTrip & { return_pct: number } => t.return_pct != null)
    .map((t) => t.return_pct * 100);

  // ── 单笔收益率分布直方图：红盈绿亏（按箱中值符号着色） ──
  const hist = rets.length > 0 ? buildHistogram(rets) : null;
  const histOption = hist && {
    tooltip: {
      trigger: "axis",
      formatter: (ps: Array<{ name: string; value: number }>) =>
        `${ps[0].name}%：${ps[0].value} 笔`,
    },
    grid: { left: 40, right: 16, top: 16, bottom: 48 },
    xAxis: {
      type: "category",
      data: hist.labels,
      name: "收益率%",
      nameLocation: "middle",
      nameGap: 34,
      axisLabel: { fontSize: 10, rotate: 30 },
    },
    yAxis: { type: "value", name: "笔数", minInterval: 1 },
    series: [
      {
        type: "bar",
        data: hist.counts.map((c, i) => ({
          value: c,
          itemStyle: { color: hist.mids[i] >= 0 ? "#ef4444" : "#10b981" },
        })),
        barCategoryGap: "10%",
      },
    ],
  };

  // ── 持仓周期 × 收益散点：盈利/亏损分两系列 ──
  const toPoint = (t: RoundTrip) => ({
    value: [t.holding_days, Number(((t.return_pct ?? 0) * 100).toFixed(2))],
    entry: t.entry_dt,
    exit: t.exit_dt,
  });
  const winPoints = trips.filter((t) => (t.pnl ?? 0) > 0).map(toPoint);
  const losePoints = trips.filter((t) => (t.pnl ?? 0) <= 0).map(toPoint);

  const scatterOption = {
    tooltip: {
      formatter: (p: { data: { value: number[]; entry: string; exit: string } }) =>
        `${p.data.entry} → ${p.data.exit}<br/>持仓 ${p.data.value[0]} 天：${p.data.value[1]}%`,
    },
    legend: { data: ["盈利", "亏损"], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 48, right: 16, top: 28, bottom: 44 },
    xAxis: { type: "value", name: "持仓天数", nameLocation: "middle", nameGap: 28, minInterval: 1 },
    yAxis: { type: "value", name: "收益率%", scale: true },
    series: [
      { name: "盈利", type: "scatter", data: winPoints, symbolSize: 9, itemStyle: { color: "#ef4444" } },
      { name: "亏损", type: "scatter", data: losePoints, symbolSize: 9, itemStyle: { color: "#10b981" } },
    ],
  };

  const holdingDetail =
    result.win_holding_days != null && result.lose_holding_days != null
      ? `盈 ${result.win_holding_days} / 亏 ${result.lose_holding_days}`
      : "-";

  return (
    <Card title="交易行为分析" size="small">
      <Row gutter={[8, 8]}>
        <Col span={6}>
          <StatCard
            label="单笔期望（元）"
            value={result.expectancy != null ? result.expectancy.toFixed(0) : "-"}
          />
        </Col>
        <Col span={6}>
          <StatCard
            label={`平均持仓（天）｜${holdingDetail}`}
            value={result.avg_holding_days != null ? result.avg_holding_days.toFixed(1) : "-"}
          />
        </Col>
        <Col span={6}>
          <StatCard label="平均 MAE" value={pct(result.avg_mae)} />
        </Col>
        <Col span={6}>
          <StatCard label="平均 MFE" value={pct(result.avg_mfe)} />
        </Col>
      </Row>
      <Row gutter={[8, 8]} className="mt-3">
        {histOption && (
          <Col xs={24} lg={12}>
            <div className="text-xs text-slate-500 mb-1">单笔收益率分布</div>
            <ReactECharts option={histOption} style={{ height: 240 }} notMerge />
          </Col>
        )}
        <Col xs={24} lg={histOption ? 12 : 24}>
          <div className="text-xs text-slate-500 mb-1">持仓周期 × 收益</div>
          <ReactECharts option={scatterOption} style={{ height: 240 }} notMerge />
        </Col>
      </Row>
    </Card>
  );
}
