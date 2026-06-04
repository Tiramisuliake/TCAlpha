import { useState } from "react";
import { Card, DatePicker, Empty, Select, Space, Spin, Table, Tag, message } from "antd";
import { useQueries, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { getBacktestStatus, submitBacktest } from "@/api/backtest";
import { getStrategyClasses } from "@/api/strategy";
import { PermButton } from "@/components/PermButton";
import type { BacktestResult, BacktestStatus } from "@/types";

const { RangePicker } = DatePicker;
const PALETTE = ["#1a4fff", "#FFB800", "#00a778", "#ef4444", "#8b5cf6", "#06b6d4"];

interface CompareJob {
  class_name: string;
  job_id: number;
}

interface CompareRow {
  class_name: string;
  status: string;
  result: BacktestResult | null;
}

/**
 * 多策略对比回测：同标的、同区间，各策略默认参数，分别提交 backtest job，
 * useQueries 并行轮询，结果用 ECharts 多曲线叠加（百分比收益）+ 指标对比表。
 * 纯前端编排，复用现有 /backtest/submit + /backtest/{id}，无后端改动。
 */
export function BacktestCompare({
  symbolOptions,
}: {
  symbolOptions: { value: string; label: string }[];
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [symbol, setSymbol] = useState<string>();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [jobs, setJobs] = useState<CompareJob[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const { data: classes = [] } = useQuery({
    queryKey: ["strategy", "classes"],
    queryFn: getStrategyClasses,
  });
  const classOptions = classes.map((c) => ({ value: c.class_name, label: c.class_name }));

  const jobQueries = useQueries({
    queries: jobs.map((j) => ({
      queryKey: ["backtest", "compare", j.job_id],
      queryFn: () => getBacktestStatus(j.job_id),
      refetchInterval: (query: { state: { data?: BacktestStatus } }) => {
        const s = query.state.data?.status;
        return s === "done" || s === "failed" ? false : 2000;
      },
    })),
  });

  const rows: CompareRow[] = jobs.map((j, i) => {
    const data = jobQueries[i]?.data;
    return {
      class_name: j.class_name,
      status: data?.status ?? "pending",
      result: data?.result ?? null,
    };
  });
  const allDone = rows.length > 0 && rows.every((r) => r.status === "done" || r.status === "failed");
  const doneResults = rows.filter(
    (r): r is CompareRow & { result: BacktestResult } => r.result !== null,
  );

  const runCompare = async () => {
    if (!symbol || !range || selected.length === 0) {
      message.warning("请选择至少一个策略、标的和回测区间");
      return;
    }
    setSubmitting(true);
    setJobs([]);
    try {
      const submitted: CompareJob[] = [];
      for (const cls of selected) {
        const schema = classes.find((c) => c.class_name === cls)?.params_schema ?? {};
        const params = Object.fromEntries(
          Object.entries(schema).map(([k, v]) => [k, v.default]),
        );
        const res = await submitBacktest({
          name: `对比_${cls}`,
          class_name: cls,
          symbol,
          params,
          start_date: range[0].format("YYYY-MM-DD"),
          end_date: range[1].format("YYYY-MM-DD"),
          init_capital: 1_000_000,
          commission_rate: 0.0003,
          slippage: 0.01,
        });
        submitted.push({ class_name: cls, job_id: res.job_id });
      }
      setJobs(submitted);
      message.success(`已提交 ${submitted.length} 个回测，计算中…`);
    } finally {
      setSubmitting(false);
    }
  };

  const dates = doneResults[0]?.result.equity_curve.map((p) => p.dt.slice(0, 10)) ?? [];
  const chartOption =
    doneResults.length > 0
      ? {
          tooltip: { trigger: "axis", valueFormatter: (v: number) => `${v}%` },
          legend: {
            data: doneResults.map((r) => r.class_name),
            top: 0,
            textStyle: { fontSize: 11 },
          },
          grid: { left: 55, right: 20, top: 35, bottom: 45 },
          xAxis: { type: "category", data: dates, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: {
            type: "value",
            name: "收益%",
            axisLabel: { formatter: "{value}%", fontSize: 10 },
          },
          series: doneResults.map((r, idx) => ({
            name: r.class_name,
            type: "line",
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2 },
            itemStyle: { color: PALETTE[idx % PALETTE.length] },
            data: r.result.equity_curve.map(
              (p) => +((p.value / r.result.init_capital - 1) * 100).toFixed(2),
            ),
          })),
        }
      : null;

  const cols: ColumnsType<CompareRow> = [
    { title: "策略", dataIndex: "class_name", key: "class_name" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 88,
      render: (s: string) => (
        <Tag color={s === "done" ? "success" : s === "failed" ? "error" : "processing"}>{s}</Tag>
      ),
    },
    {
      title: "总收益",
      key: "ret",
      align: "right",
      render: (_, r) =>
        r.result ? (
          <span className={`num ${r.result.total_return >= 0 ? "up" : "down"}`}>
            {(r.result.total_return * 100).toFixed(2)}%
          </span>
        ) : (
          "-"
        ),
    },
    {
      title: "年化",
      key: "ann",
      align: "right",
      render: (_, r) =>
        r.result ? <span className="num">{(r.result.annual_return * 100).toFixed(2)}%</span> : "-",
    },
    {
      title: "夏普",
      key: "sharpe",
      align: "right",
      render: (_, r) => (r.result ? <span className="num">{r.result.sharpe.toFixed(2)}</span> : "-"),
    },
    {
      title: "最大回撤",
      key: "dd",
      align: "right",
      render: (_, r) =>
        r.result ? (
          <span className="num down">{(r.result.max_drawdown * 100).toFixed(2)}%</span>
        ) : (
          "-"
        ),
    },
    {
      title: "胜率",
      key: "wr",
      align: "right",
      render: (_, r) =>
        r.result ? <span className="num">{(r.result.win_rate * 100).toFixed(1)}%</span> : "-",
    },
    {
      title: "交易数",
      key: "tc",
      align: "right",
      render: (_, r) => (r.result ? <span className="num">{r.result.trade_count}</span> : "-"),
    },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-auto">
      <Card size="small" title="多策略对比（同标的同区间 · 各策略默认参数）">
        <Space wrap>
          <Select
            mode="multiple"
            placeholder="选择策略（可多选）"
            options={classOptions}
            value={selected}
            onChange={setSelected}
            style={{ minWidth: 280 }}
            maxTagCount="responsive"
          />
          <Select
            showSearch
            placeholder="标的"
            options={symbolOptions}
            value={symbol}
            onChange={setSymbol}
            filterOption={(input, opt) =>
              ((opt?.label as string) ?? "").toLowerCase().includes(input.toLowerCase())
            }
            style={{ width: 200 }}
          />
          <RangePicker value={range} onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)} />
          <PermButton perm="backtest.run" type="primary" loading={submitting} onClick={runCompare}>
            开始对比
          </PermButton>
        </Space>
      </Card>

      {jobs.length === 0 ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
          <Empty description="选择多个策略后开始对比回测" />
        </Card>
      ) : (
        <>
          <Card size="small" title={`收益对比${allDone ? "" : "（计算中…）"}`}>
            {chartOption ? (
              <ReactECharts option={chartOption} style={{ height: 320 }} notMerge />
            ) : (
              <div className="h-40 flex items-center justify-center text-slate-400 gap-2">
                <Spin />
                <span>回测计算中…</span>
              </div>
            )}
          </Card>
          <Card size="small" title="指标对比">
            <Table<CompareRow>
              rowKey="class_name"
              size="small"
              dataSource={rows}
              columns={cols}
              pagination={false}
            />
          </Card>
        </>
      )}
    </div>
  );
}
