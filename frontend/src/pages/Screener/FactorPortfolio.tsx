import { useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Card, Empty, InputNumber, Statistic, Tooltip, message } from "antd";
import { FundOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { runFactorPortfolio } from "@/api/screener";
import type { FactorWeights } from "@/types";
import { DEFAULT_FACTOR_WEIGHTS, FACTORS } from "./factorMeta";

function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </div>
  );
}

const UP = "#ef4444";
const DOWN = "#10b981";
const WARN = "#f59e0b";

/**
 * 多因子组合回测：用因子综合分历史每调仓日选 top_n 等权持有，拼组合净值并对比全市场等权基准。
 * 把「多因子选股」从当前截面延伸到历史收益验证——选出的因子组合到底赚不赚钱。
 */
export default function FactorPortfolio() {
  const [weights, setWeights] = useState<FactorWeights>(DEFAULT_FACTOR_WEIGHTS);
  const [topN, setTopN] = useState(10);
  const [rebalanceDays, setRebalanceDays] = useState(20);
  const [lookback, setLookback] = useState(480);

  const mut = useMutation({
    mutationFn: runFactorPortfolio,
    onSuccess: (res) => {
      if (!res.ready) message.info("尚无足够历史 K 线，请先到「数据」页下载日 K");
      else if (res.rebalance_count === 0)
        message.info("有效标的不足（少于持仓数），请调大扫描上限或减小持仓数");
      else message.success(`回测完成（${res.rebalance_count} 次调仓）`);
    },
  });
  const res = mut.data;

  const setWeight = (key: keyof FactorWeights, v: number) =>
    setWeights((p) => ({ ...p, [key]: v }));
  const run = () =>
    mut.mutate({ weights, top_n: topN, rebalance_days: rebalanceDays, lookback });

  const hasCurve = !!res?.ready && res.equity_curve.length > 0;
  const chartOption = hasCurve
    ? {
        tooltip: { trigger: "axis" },
        legend: { data: ["组合", "全市场等权"], top: 0, textStyle: { fontSize: 11 } },
        grid: { left: 52, right: 16, top: 28, bottom: 44 },
        xAxis: {
          type: "category",
          data: res.equity_curve.map((p) => p.dt),
          axisLabel: { rotate: 30, fontSize: 10 },
        },
        yAxis: { type: "value", scale: true },
        series: [
          {
            name: "组合",
            type: "line",
            data: res.equity_curve.map((p) => p.value),
            smooth: true,
            symbol: "none",
            lineStyle: { color: "#3b82f6", width: 2 },
          },
          {
            name: "全市场等权",
            type: "line",
            data: res.benchmark_curve.map((p) => p.value),
            smooth: true,
            symbol: "none",
            lineStyle: { color: "#94a3b8", width: 1.5, type: "dashed" },
          },
        ],
      }
    : null;

  return (
    <>
      <Card size="small" title="多因子组合回测（top_n 等权 + 定期调仓 + 全市场基准对比）">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          {FACTORS.map((f) => (
            <Field key={f.key} label={<Tooltip title={f.desc}>{f.label}权重</Tooltip>}>
              <InputNumber
                size="small"
                min={0}
                max={10}
                step={0.5}
                style={{ width: 78 }}
                value={weights[f.key]}
                onChange={(v) => setWeight(f.key, v ?? 0)}
              />
            </Field>
          ))}
          <Field label="持仓数(top_n)">
            <InputNumber size="small" min={1} max={100} value={topN} onChange={(v) => setTopN(v ?? 10)} />
          </Field>
          <Field label="调仓周期(日)">
            <InputNumber size="small" min={1} max={120} value={rebalanceDays} onChange={(v) => setRebalanceDays(v ?? 20)} />
          </Field>
          <Field label="回看窗口(日)">
            <InputNumber size="small" min={40} max={2000} value={lookback} onChange={(v) => setLookback(v ?? 480)} />
          </Field>
          <Button type="primary" icon={<FundOutlined />} loading={mut.isPending} onClick={run}>
            组合回测
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          历史每隔「调仓周期」按因子综合分选 top_n 只等权持有到下次调仓，拼出组合净值并对比全市场等权基准。净值为调仓粒度；夏普按调仓收益序列年化。权重置 0 即排除该因子。
        </div>
      </Card>

      {res && !res.ready && (
        <Alert type="info" showIcon message="历史 K 线不足以回测（需覆盖回看窗口 + 调仓周期），请先到「数据」页下载日 K" />
      )}

      {res?.ready && res.rebalance_count > 0 && (
        <Card size="small">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
            <Statistic
              title="总收益"
              value={res.total_return * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: res.total_return >= 0 ? UP : DOWN, fontSize: 18 }}
            />
            <Statistic
              title="年化收益"
              value={res.annual_return * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: res.annual_return >= 0 ? UP : DOWN, fontSize: 18 }}
            />
            <Statistic title="夏普" value={res.sharpe} precision={2} valueStyle={{ fontSize: 18 }} />
            <Statistic
              title="最大回撤"
              value={res.max_drawdown * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: WARN, fontSize: 18 }}
            />
            <Statistic title="调仓胜率" value={res.win_rate * 100} precision={1} suffix="%" valueStyle={{ fontSize: 18 }} />
            <Statistic
              title="对基准超额"
              value={res.excess_return * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: res.excess_return >= 0 ? UP : DOWN, fontSize: 18 }}
            />
            <Statistic title="调仓次数" value={res.rebalance_count} valueStyle={{ fontSize: 18 }} />
          </div>
        </Card>
      )}

      {hasCurve && chartOption ? (
        <Card
          size="small"
          title={`组合净值 vs 全市场等权（top ${res.top_n} 等权，每 ${rebalanceDays} 日调仓）`}
          className="flex-1"
          classNames={{ body: "flex-1 min-h-0" }}
        >
          <ReactECharts option={chartOption} style={{ height: "100%", minHeight: 300 }} notMerge />
        </Card>
      ) : (
        !res && (
          <Card size="small" className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
            <Empty description="设权重与参数后点「组合回测」" />
          </Card>
        )
      )}
    </>
  );
}
