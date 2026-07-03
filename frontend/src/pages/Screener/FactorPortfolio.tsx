import { useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Card, Divider, Drawer, Empty, InputNumber, Popconfirm, Select, Statistic, Table, Tooltip, message } from "antd";
import { DeleteOutlined, DownloadOutlined, ExperimentOutlined, FundOutlined, HistoryOutlined, RadarChartOutlined, SaveOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import ReactECharts from "echarts-for-react";
import {
  deletePortfolioRecord,
  downloadPortfolioReport,
  listPortfolioRecords,
  runFactorPortfolio,
  runFactorPortfolioSweep,
  runFactorWalkforward,
  savePortfolioRecord,
} from "@/api/screener";
import type { FactorWeights, PortfolioRecord } from "@/types";
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

interface WfRow {
  k: string;
  is: number;
  oos: number;
  pct: boolean;
}

/** walk-forward 对比单元格：百分比/数值 + 涨跌色，衰减列带符号。 */
function fmtSeg(v: number, pct: boolean, signed = false): ReactNode {
  const num = pct ? `${(v * 100).toFixed(2)}%` : v.toFixed(2);
  return <span className={`num ${v >= 0 ? "up" : "down"}`}>{signed && v > 0 ? `+${num}` : num}</span>;
}

const WF_COLS: ColumnsType<WfRow> = [
  { title: "指标", dataIndex: "k", width: 96 },
  { title: "样本内 IS", dataIndex: "is", align: "right", render: (v, r) => fmtSeg(v as number, r.pct) },
  { title: "样本外 OOS", dataIndex: "oos", align: "right", render: (v, r) => fmtSeg(v as number, r.pct) },
  { title: "衰减(OOS-IS)", key: "decay", align: "right", render: (_, r) => fmtSeg(r.oos - r.is, r.pct, true) },
];

const SWEEP_METRICS = [
  { value: "sharpe", label: "夏普" },
  { value: "annual_return", label: "年化收益" },
  { value: "excess_return", label: "超额收益" },
] as const;
type SweepMetric = (typeof SWEEP_METRICS)[number]["value"];

/**
 * 多因子组合回测 + 参数寻优：用因子综合分历史每调仓日选 top_n 等权持有，对比全市场基准；
 * 并对 top_n × rebalance_days 网格扫描找最优组合配置（热力图参数地图）。
 */
export default function FactorPortfolio() {
  const [weights, setWeights] = useState<FactorWeights>(DEFAULT_FACTOR_WEIGHTS);
  const [topN, setTopN] = useState(10);
  const [rebalanceDays, setRebalanceDays] = useState(20);
  const [lookback, setLookback] = useState(480);

  // 寻优参数
  const [topNList, setTopNList] = useState<number[]>([10, 20, 30]);
  const [rebalanceList, setRebalanceList] = useState<number[]>([10, 20, 40]);
  const [sweepMetric, setSweepMetric] = useState<SweepMetric>("sharpe");

  const setWeight = (key: keyof FactorWeights, v: number) =>
    setWeights((p) => ({ ...p, [key]: v }));

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

  const sweepMut = useMutation({
    mutationFn: runFactorPortfolioSweep,
    onSuccess: (cells) => {
      if (!cells.length) message.info("无有效寻优结果，请检查参数或先下载数据");
      else message.success(`寻优完成（${cells.length} 组合）`);
    },
  });
  const sweepCells = sweepMut.data ?? [];

  const exportMut = useMutation({
    mutationFn: downloadPortfolioReport,
    onError: () => message.error("导出失败，请重试"),
  });

  // 历史存档
  const qc = useQueryClient();
  const [historyOpen, setHistoryOpen] = useState(false);
  const { data: records } = useQuery({
    queryKey: ["portfolio-records"],
    queryFn: listPortfolioRecords,
    enabled: historyOpen,
  });
  const saveMut = useMutation({
    mutationFn: savePortfolioRecord,
    onSuccess: () => {
      message.success("已存档");
      qc.invalidateQueries({ queryKey: ["portfolio-records"] });
    },
  });
  const delMut = useMutation({
    mutationFn: deletePortfolioRecord,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio-records"] }),
  });

  const recordCols: ColumnsType<PortfolioRecord> = [
    { title: "名称", dataIndex: "name", ellipsis: true },
    {
      title: "夏普",
      key: "sharpe",
      align: "right",
      render: (_, r) => <span className="num">{(r.metrics.sharpe ?? 0).toFixed(2)}</span>,
    },
    {
      title: "年化",
      key: "annual",
      align: "right",
      render: (_, r) => {
        const v = r.metrics.annual_return ?? 0;
        return <span className={`num ${v >= 0 ? "up" : "down"}`}>{(v * 100).toFixed(1)}%</span>;
      },
    },
    {
      title: "超额",
      key: "excess",
      align: "right",
      render: (_, r) => {
        const v = r.metrics.excess_return ?? 0;
        return <span className={`num ${v >= 0 ? "up" : "down"}`}>{(v * 100).toFixed(1)}%</span>;
      },
    },
    { title: "时间", dataIndex: "created_at", width: 96, render: (v: string) => v.slice(0, 10) },
    {
      title: "",
      key: "del",
      width: 42,
      render: (_, r) => (
        <Popconfirm title="删除该存档？" onConfirm={() => delMut.mutate(r.id)}>
          <Button size="small" type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  const [oosRatio, setOosRatio] = useState(0.3);
  const wfMut = useMutation({
    mutationFn: runFactorWalkforward,
    onSuccess: (r) => {
      if (!r.ready) message.info("尚无足够历史 K 线，请先到「数据」页下载日 K");
      else if (!r.in_curve.length) message.info("调仓点不足以切分样本内/外，请增大回看窗口");
      else message.success("样本外验证完成");
    },
  });
  const wf = wfMut.data;

  const runOnce = () =>
    mut.mutate({ weights, top_n: topN, rebalance_days: rebalanceDays, lookback });
  const runSweep = () =>
    sweepMut.mutate({ weights, top_n_list: topNList, rebalance_list: rebalanceList, lookback });
  const runWalkforward = () =>
    wfMut.mutate({ weights, top_n: topN, rebalance_days: rebalanceDays, lookback, oos_ratio: oosRatio });

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

  const heatOption =
    sweepCells.length > 0
      ? (() => {
          const topNs = [...new Set(sweepCells.map((c) => c.top_n))].sort((a, b) => a - b);
          const rebals = [...new Set(sweepCells.map((c) => c.rebalance_days))].sort((a, b) => a - b);
          const data = sweepCells.map((c) => [
            topNs.indexOf(c.top_n),
            rebals.indexOf(c.rebalance_days),
            Number((sweepMetric === "sharpe" ? c.sharpe : c[sweepMetric] * 100).toFixed(2)),
          ]);
          const vals = data.map((d) => d[2]);
          return {
            tooltip: { position: "top" },
            grid: { left: 60, right: 20, top: 16, bottom: 58 },
            xAxis: { type: "category", data: topNs.map(String), name: "持仓数", nameLocation: "middle", nameGap: 26 },
            yAxis: { type: "category", data: rebals.map(String), name: "调仓日" },
            visualMap: {
              min: Math.min(...vals),
              max: Math.max(...vals),
              calculable: true,
              orient: "horizontal",
              left: "center",
              bottom: 6,
              inRange: { color: [DOWN, "#fde68a", UP] },
            },
            series: [
              {
                type: "heatmap",
                data,
                label: { show: true, fontSize: 11 },
                emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.3)" } },
              },
            ],
          };
        })()
      : null;

  const wfChartOption =
    wf?.ready && wf.in_curve.length > 0
      ? {
          tooltip: { trigger: "axis" },
          legend: { data: ["样本内", "样本外"], top: 0, textStyle: { fontSize: 11 } },
          grid: { left: 44, right: 16, top: 28, bottom: 40 },
          xAxis: {
            type: "category",
            data: [...wf.in_curve.map((p) => p.dt), ...wf.out_curve.map((p) => p.dt)],
            axisLabel: { rotate: 30, fontSize: 10 },
          },
          yAxis: { type: "value", scale: true },
          series: [
            {
              name: "样本内",
              type: "line",
              data: [...wf.in_curve.map((p) => p.value), ...wf.out_curve.map(() => null)],
              smooth: true,
              symbol: "none",
              lineStyle: { color: "#3b82f6", width: 2 },
            },
            {
              name: "样本外",
              type: "line",
              data: [...wf.in_curve.map(() => null), ...wf.out_curve.map((p) => p.value)],
              smooth: true,
              symbol: "none",
              lineStyle: { color: WARN, width: 2 },
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
        </div>
        <Divider className="!my-3" />
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <Field label="持仓数(top_n)">
            <InputNumber size="small" min={1} max={100} value={topN} onChange={(v) => setTopN(v ?? 10)} />
          </Field>
          <Field label="调仓周期(日)">
            <InputNumber size="small" min={1} max={120} value={rebalanceDays} onChange={(v) => setRebalanceDays(v ?? 20)} />
          </Field>
          <Field label="回看窗口(日)">
            <InputNumber size="small" min={40} max={2000} value={lookback} onChange={(v) => setLookback(v ?? 480)} />
          </Field>
          <Button type="primary" icon={<FundOutlined />} loading={mut.isPending} onClick={runOnce}>
            单次回测
          </Button>
          <Field label="样本外占比">
            <InputNumber size="small" min={0.1} max={0.5} step={0.05} value={oosRatio} onChange={(v) => setOosRatio(v ?? 0.3)} />
          </Field>
          <Button icon={<ExperimentOutlined />} loading={wfMut.isPending} onClick={runWalkforward}>
            样本外验证
          </Button>
          <Divider type="vertical" className="!h-8" />
          <Field label="持仓数网格">
            <Select
              mode="tags"
              size="small"
              style={{ minWidth: 150 }}
              value={topNList.map(String)}
              onChange={(vals) => setTopNList(vals.map(Number).filter((n) => n > 0))}
              placeholder="如 10,20,30"
              tokenSeparators={[",", " "]}
            />
          </Field>
          <Field label="调仓周期网格">
            <Select
              mode="tags"
              size="small"
              style={{ minWidth: 150 }}
              value={rebalanceList.map(String)}
              onChange={(vals) => setRebalanceList(vals.map(Number).filter((n) => n > 0))}
              placeholder="如 10,20,40"
              tokenSeparators={[",", " "]}
            />
          </Field>
          <Field label="寻优指标">
            <Select
              size="small"
              style={{ width: 110 }}
              value={sweepMetric}
              onChange={setSweepMetric}
              options={SWEEP_METRICS.map((m) => ({ value: m.value, label: m.label }))}
            />
          </Field>
          <Button icon={<RadarChartOutlined />} loading={sweepMut.isPending} onClick={runSweep}>
            参数寻优
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          单次回测用上方权重 + 单组参数；参数寻优对「持仓数网格 × 调仓周期网格」笛卡尔积各跑一次，按所选指标画热力图找最优配置（色越红越优）。同一调仓周期下不同持仓数共享因子计算。
        </div>
      </Card>

      {res && !res.ready && (
        <Alert type="info" showIcon message="历史 K 线不足以回测（需覆盖回看窗口 + 调仓周期），请先到「数据」页下载日 K" />
      )}

      {res?.ready && res.rebalance_count > 0 && (
        <Card size="small">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
            <Statistic title="总收益" value={res.total_return * 100} precision={2} suffix="%" valueStyle={{ color: res.total_return >= 0 ? UP : DOWN, fontSize: 18 }} />
            <Statistic title="年化收益" value={res.annual_return * 100} precision={2} suffix="%" valueStyle={{ color: res.annual_return >= 0 ? UP : DOWN, fontSize: 18 }} />
            <Statistic title="夏普" value={res.sharpe} precision={2} valueStyle={{ fontSize: 18 }} />
            <Statistic title="最大回撤" value={res.max_drawdown * 100} precision={2} suffix="%" valueStyle={{ color: WARN, fontSize: 18 }} />
            <Statistic title="调仓胜率" value={res.win_rate * 100} precision={1} suffix="%" valueStyle={{ fontSize: 18 }} />
            <Statistic title="对基准超额" value={res.excess_return * 100} precision={2} suffix="%" valueStyle={{ color: res.excess_return >= 0 ? UP : DOWN, fontSize: 18 }} />
            <Statistic title="调仓次数" value={res.rebalance_count} valueStyle={{ fontSize: 18 }} />
          </div>
        </Card>
      )}

      {hasCurve && chartOption && (
        <Card
          size="small"
          title={`组合净值 vs 全市场等权（top ${res.top_n}，每 ${rebalanceDays} 日调仓）`}
          extra={
            <div className="flex gap-2">
              <Button
                size="small"
                icon={<SaveOutlined />}
                loading={saveMut.isPending}
                onClick={() =>
                  res &&
                  saveMut.mutate({
                    name: `top${res.top_n}/${rebalanceDays}d 组合`,
                    kind: "backtest",
                    config: { weights, top_n: topN, rebalance_days: rebalanceDays, lookback },
                    metrics: {
                      total_return: res.total_return,
                      annual_return: res.annual_return,
                      sharpe: res.sharpe,
                      max_drawdown: res.max_drawdown,
                      win_rate: res.win_rate,
                      excess_return: res.excess_return,
                      rebalance_count: res.rebalance_count,
                    },
                  })
                }
              >
                存档
              </Button>
              <Button size="small" icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
                历史
              </Button>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                loading={exportMut.isPending}
                onClick={() =>
                  exportMut.mutate({ weights, top_n: topN, rebalance_days: rebalanceDays, lookback })
                }
              >
                导出报告
              </Button>
            </div>
          }
        >
          <ReactECharts option={chartOption} style={{ height: 300 }} notMerge />
        </Card>
      )}

      {wf?.ready && wf.in_curve.length > 0 && (
        <Card
          size="small"
          title={`样本外验证（IS ${wf.split_index} 段 / OOS ${wf.rebalance_count - wf.split_index} 段 · 分割于 ${wf.split_date}）`}
        >
          <Table<WfRow>
            size="small"
            pagination={false}
            rowKey="k"
            columns={WF_COLS}
            dataSource={[
              { k: "总收益", is: wf.in_sample.total_return, oos: wf.out_sample.total_return, pct: true },
              { k: "年化收益", is: wf.in_sample.annual_return, oos: wf.out_sample.annual_return, pct: true },
              { k: "夏普", is: wf.in_sample.sharpe, oos: wf.out_sample.sharpe, pct: false },
              { k: "最大回撤", is: wf.in_sample.max_drawdown, oos: wf.out_sample.max_drawdown, pct: true },
              { k: "对基准超额", is: wf.in_sample.excess_return, oos: wf.out_sample.excess_return, pct: true },
            ]}
          />
          <div className="mt-3">
            {wfChartOption && <ReactECharts option={wfChartOption} style={{ height: 260 }} notMerge />}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            样本内 / 外净值各从 1 起；OOS 指标显著低于 IS（衰减为负且大）提示参数过拟合，配置在未来未必成立。
          </div>
        </Card>
      )}

      {heatOption ? (
        <Card
          size="small"
          title={`参数寻优热力图（${SWEEP_METRICS.find((m) => m.value === sweepMetric)?.label}，色越红越优）`}
          className="flex-1"
          classNames={{ body: "flex-1 min-h-0" }}
        >
          <ReactECharts option={heatOption} style={{ height: "100%", minHeight: 320 }} notMerge />
        </Card>
      ) : (
        !res && (
          <Card size="small" className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
            <Empty description="设权重与参数后「单次回测」看净值，或「参数寻优」找最优配置" />
          </Card>
        )
      )}

      <Drawer
        title="回测历史存档（配置 + 绩效快照，可对比多次结果）"
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        width={560}
      >
        <Table<PortfolioRecord>
          size="small"
          rowKey="id"
          columns={recordCols}
          dataSource={records ?? []}
          pagination={false}
          locale={{ emptyText: "暂无存档——单次回测后点「存档」保存" }}
        />
      </Drawer>
    </>
  );
}
