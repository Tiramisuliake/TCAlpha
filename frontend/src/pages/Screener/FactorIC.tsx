import { useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Card, Empty, InputNumber, Select, Space, Statistic, Table, Tag, Tooltip, message } from "antd";
import { ExperimentOutlined, TableOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import ReactECharts from "echarts-for-react";
import { runFactorIC, runFactorICAll } from "@/api/screener";
import type { FactorICSummary } from "@/types";
import { FACTORS } from "./factorMeta";

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

/** 按 |平均 IC| 强度判定因子有效性。 */
function icVerdict(meanIc: number) {
  const ic = Math.abs(meanIc);
  if (ic >= 0.05) return { color: "red", short: "强", long: "强有效" };
  if (ic >= 0.03) return { color: "orange", short: "弱", long: "弱有效" };
  return { color: "default", short: "噪声", long: "噪声为主" };
}

/**
 * 单因子有效性检验：对回看窗口内多个采样时点，算因子值与未来收益的横截面 rank IC，
 * 并按因子值分 5 档看未来收益单调性。支持单因子细查（IC 卡 + 分层图）与全因子横评对比。
 */
export default function FactorIC() {
  const [factor, setFactor] = useState("mom_20");
  const [holdDays, setHoldDays] = useState(10);
  const [lookback, setLookback] = useState(240);
  const [samplePoints, setSamplePoints] = useState(8);

  const mut = useMutation({
    mutationFn: runFactorIC,
    onSuccess: (res) => {
      if (!res.ready) message.info("尚无足够历史 K 线，请先到「数据」页下载日 K");
      else message.success(`检验完成（${res.sample_count} 个采样时点）`);
    },
  });
  const res = mut.data;

  const allMut = useMutation({
    mutationFn: runFactorICAll,
    onSuccess: (rows) => {
      if (!rows.some((r) => r.sample_count > 0))
        message.info("尚无足够历史 K 线，请先到「数据」页下载日 K");
      else message.success("全因子横评完成");
    },
  });
  const allRows = allMut.data ?? [];

  const params = { hold_days: holdDays, lookback, sample_points: samplePoints };
  const runOne = () => mut.mutate({ factor, ...params });
  const runAll = () => allMut.mutate(params);

  const factorLabel = FACTORS.find((f) => f.key === factor)?.label ?? factor;
  const verdict = res?.ready ? icVerdict(res.mean_ic) : null;

  const allCols: ColumnsType<FactorICSummary> = [
    { title: "因子", dataIndex: "name", width: 92 },
    {
      title: "平均 IC",
      dataIndex: "mean_ic",
      align: "right",
      sorter: (a, b) => Math.abs(a.mean_ic) - Math.abs(b.mean_ic),
      render: (v: number) => <span className={`num ${v >= 0 ? "up" : "down"}`}>{v.toFixed(4)}</span>,
    },
    {
      title: "IC_IR",
      dataIndex: "ic_ir",
      align: "right",
      sorter: (a, b) => a.ic_ir - b.ic_ir,
      render: (v: number) => <span className="num">{v.toFixed(3)}</span>,
    },
    {
      title: "IC胜率",
      dataIndex: "ic_win_rate",
      align: "right",
      render: (v: number) => <span className="num">{(v * 100).toFixed(0)}%</span>,
    },
    {
      title: "多空收益",
      dataIndex: "long_short",
      align: "right",
      defaultSortOrder: "descend",
      sorter: (a, b) => a.long_short - b.long_short,
      render: (v: number) => <span className={`num ${v >= 0 ? "up" : "down"}`}>{(v * 100).toFixed(2)}%</span>,
    },
    {
      title: "有效性",
      key: "verdict",
      align: "center",
      render: (_: unknown, r: FactorICSummary) => {
        const vd = icVerdict(r.mean_ic);
        return <Tag color={vd.color} className="!m-0">{vd.short}</Tag>;
      },
    },
    {
      title: "采样",
      dataIndex: "sample_count",
      align: "right",
      render: (v: number) => <span className="num text-slate-400">{v}</span>,
    },
  ];

  const chartOption = res?.ready
    ? {
        grid: { left: 56, right: 16, top: 16, bottom: 28 },
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: res.quantiles.map((q) => `Q${q.q}`) },
        yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
        series: [
          {
            type: "bar",
            barWidth: "55%",
            data: res.quantiles.map((q) => ({
              value: Number((q.avg_return * 100).toFixed(2)),
              itemStyle: { color: q.avg_return >= 0 ? UP : DOWN },
            })),
          },
        ],
      }
    : null;

  return (
    <>
      <Card size="small" title="单因子有效性检验（IC + 5 档分层回测）">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <Field label="因子（单因子细查）">
            <Select
              size="small"
              style={{ width: 130 }}
              value={factor}
              onChange={setFactor}
              options={FACTORS.map((f) => ({ value: f.key, label: f.label }))}
            />
          </Field>
          <Field label="持有天数">
            <InputNumber size="small" min={1} max={60} value={holdDays} onChange={(v) => setHoldDays(v ?? 10)} />
          </Field>
          <Field label="回看窗口(日)">
            <InputNumber size="small" min={40} max={1000} value={lookback} onChange={(v) => setLookback(v ?? 240)} />
          </Field>
          <Field label="采样点数">
            <InputNumber size="small" min={3} max={30} value={samplePoints} onChange={(v) => setSamplePoints(v ?? 8)} />
          </Field>
          <Space>
            <Button type="primary" icon={<ExperimentOutlined />} loading={mut.isPending} onClick={runOne}>
              单因子检验
            </Button>
            <Button icon={<TableOutlined />} loading={allMut.isPending} onClick={runAll}>
              全因子横评
            </Button>
          </Space>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          对回看窗口内多个采样时点，算因子值与未来 N 日收益的横截面 rank IC（秩相关），并按因子值分 5
          档看收益单调性。IC 符号随因子方向（动量正 / 反转负）；|IC| ≥ 0.03 弱有效、≥ 0.05 强；IC_IR
          ≥ 0.3 较稳定；多空收益已按因子方向对齐（&gt; 0 表示有效）。
        </div>
      </Card>

      {allRows.length > 0 && (
        <Card size="small" title="全因子 IC 横评（按多空收益降序，点列头可改排序）">
          <Table<FactorICSummary>
            rowKey="factor"
            size="small"
            dataSource={allRows}
            columns={allCols}
            pagination={false}
          />
        </Card>
      )}

      {res && !res.ready && (
        <Alert type="info" showIcon message="历史 K 线不足以检验（需覆盖回看窗口 + 持有期），请先到「数据」页下载日 K" />
      )}

      {res?.ready && (
        <Card size="small">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
            <Statistic
              title="平均 IC"
              value={res.mean_ic}
              precision={4}
              valueStyle={{ color: res.mean_ic >= 0 ? UP : DOWN, fontSize: 18 }}
            />
            <Statistic title="IC_IR（信息比率）" value={res.ic_ir} precision={3} valueStyle={{ fontSize: 18 }} />
            <Statistic title="IC 胜率" value={res.ic_win_rate * 100} precision={1} suffix="%" valueStyle={{ fontSize: 18 }} />
            <Statistic
              title="多空收益(Q5-Q1)"
              value={res.long_short * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: res.long_short >= 0 ? UP : DOWN, fontSize: 18 }}
            />
            <Statistic title="采样时点" value={res.sample_count} valueStyle={{ fontSize: 18 }} />
            {verdict && (
              <Tooltip title="基于 |平均 IC| 强度判定">
                <Tag color={verdict.color} className="text-sm">{verdict.long}</Tag>
              </Tooltip>
            )}
          </div>
        </Card>
      )}

      {res?.ready && chartOption ? (
        <Card
          size="small"
          title={`分层未来收益（${factorLabel}，持有 ${res.hold_days} 日 · Q1 因子值最低 → Q5 最高）`}
          className="flex-1"
          classNames={{ body: "flex-1 min-h-0" }}
        >
          <ReactECharts option={chartOption} style={{ height: "100%", minHeight: 280 }} notMerge />
        </Card>
      ) : (
        !res &&
        allRows.length === 0 && (
          <Card size="small" className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
            <Empty description="设参数后点「单因子检验」细查，或「全因子横评」对比" />
          </Card>
        )
      )}
    </>
  );
}
