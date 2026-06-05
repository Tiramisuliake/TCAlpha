import { useEffect, useState } from "react";
import {
  Card,
  DatePicker,
  Empty,
  InputNumber,
  Select,
  Space,
  Spin,
  Table,
  message,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { getSweepStatus, submitSweep } from "@/api/backtest";
import { getStrategyClasses } from "@/api/strategy";
import { PermButton } from "@/components/PermButton";
import type { SweepResultRow, SweepStatus } from "@/types";

const { RangePicker } = DatePicker;

const TARGETS = [
  { value: "sharpe", label: "夏普比率" },
  { value: "total_return", label: "总收益" },
  { value: "annual_return", label: "年化收益" },
  { value: "win_rate", label: "胜率" },
];

const MAX_COMBOS = 500;

interface Range {
  min: number;
  max: number;
  step: number;
}

/**
 * 网格扫参（参数寻优）：选策略 → 配每个参数的 [起始,结束,步长] → 笛卡尔积提交，
 * 后端 Celery 逐组回测，按 target 排序。结果：最优卡 + 排序表 + 2 参数热力图。
 * 复用 /backtest/sweep/* 接口。
 */
export function ParamSweep({
  symbolOptions,
}: {
  symbolOptions: { value: string; label: string }[];
}) {
  const [cls, setCls] = useState<string>();
  const [symbol, setSymbol] = useState<string>();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [target, setTarget] = useState("sharpe");
  const [ranges, setRanges] = useState<Record<string, Range>>({});
  const [jobId, setJobId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { data: classes = [] } = useQuery({
    queryKey: ["strategy", "classes"],
    queryFn: getStrategyClasses,
  });
  const classOptions = classes.map((c) => ({ value: c.class_name, label: c.class_name }));
  const schema = classes.find((c) => c.class_name === cls)?.params_schema;

  // 选策略后用 schema 默认值初始化每参数范围（min=max=default，避免一上来组合爆炸）
  useEffect(() => {
    if (!schema) {
      setRanges({});
      return;
    }
    const init: Record<string, Range> = {};
    for (const [name, def] of Object.entries(schema)) {
      const d = typeof def.default === "number" ? def.default : 0;
      init[name] = { min: d, max: d, step: def.type.includes("int") ? 1 : 0.1 };
    }
    setRanges(init);
  }, [cls]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildList = (r: Range): number[] => {
    if (r.step <= 0 || r.max < r.min) return [r.min];
    const out: number[] = [];
    for (let v = r.min; v <= r.max + 1e-9; v += r.step) out.push(+v.toFixed(6));
    return out.length ? out : [r.min];
  };

  const grid: Record<string, number[]> = {};
  for (const [name, r] of Object.entries(ranges)) grid[name] = buildList(r);
  const comboCount = Object.values(grid).reduce((acc, l) => acc * l.length, 1);

  const { data: status } = useQuery({
    queryKey: ["sweep", jobId],
    queryFn: () => getSweepStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (q: { state: { data?: SweepStatus } }) => {
      const s = q.state.data?.status;
      return s === "done" || s === "failed" ? false : 2000;
    },
  });

  const runSweep = async () => {
    if (!cls || !symbol || !range || Object.keys(grid).length === 0) {
      message.warning("请选择策略、标的和区间");
      return;
    }
    if (comboCount > MAX_COMBOS) {
      message.warning(`参数组合 ${comboCount} 过多（上限 ${MAX_COMBOS}），请缩小范围或增大步长`);
      return;
    }
    setSubmitting(true);
    setJobId(null);
    try {
      const res = await submitSweep({
        name: `寻优_${cls}`,
        class_name: cls,
        symbol,
        param_grid: grid,
        target,
        start_date: range[0].format("YYYY-MM-DD"),
        end_date: range[1].format("YYYY-MM-DD"),
        init_capital: 1_000_000,
        commission_rate: 0.0003,
        slippage: 0.01,
      });
      setJobId(res.job_id);
      message.success(`已提交寻优（${comboCount} 组），计算中…`);
    } finally {
      setSubmitting(false);
    }
  };

  const result = status?.result ?? null;
  const rows = result?.results ?? [];

  // 热力图：恰好 2 个参数维度时绘制
  const heatOption = (() => {
    if (!result || result.param_keys.length !== 2) return null;
    const [px, py] = result.param_keys;
    const xs = [...new Set(result.results.map((r) => r.params[px]))].sort((a, b) => a - b);
    const ys = [...new Set(result.results.map((r) => r.params[py]))].sort((a, b) => a - b);
    const metricOf = (r: SweepResultRow) =>
      (r.metrics as Record<string, number>)[result.target] ?? 0;
    const data = result.results.map((r) => [
      xs.indexOf(r.params[px]),
      ys.indexOf(r.params[py]),
      +metricOf(r).toFixed(3),
    ]);
    const vals = data.map((d) => d[2]);
    return {
      tooltip: {},
      grid: { left: 55, right: 20, top: 20, bottom: 55 },
      xAxis: { type: "category", data: xs.map(String), name: px, nameLocation: "middle", nameGap: 28 },
      yAxis: { type: "category", data: ys.map(String), name: py },
      visualMap: {
        min: Math.min(...vals),
        max: Math.max(...vals),
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        inRange: { color: ["#dbeafe", "#1a4fff", "#FFB800"] },
      },
      series: [
        {
          type: "heatmap",
          data,
          label: { show: true, fontSize: 10, formatter: (p: { value: number[] }) => p.value[2] },
        },
      ],
    };
  })();

  const cols: ColumnsType<SweepResultRow> = [
    {
      title: "参数",
      key: "params",
      render: (_, r) => (
        <span className="num text-xs">
          {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join("  ")}
        </span>
      ),
    },
    {
      title: "总收益",
      key: "ret",
      align: "right",
      render: (_, r) => (
        <span className={`num ${r.metrics.total_return >= 0 ? "up" : "down"}`}>
          {(r.metrics.total_return * 100).toFixed(2)}%
        </span>
      ),
    },
    {
      title: "夏普",
      key: "sharpe",
      align: "right",
      render: (_, r) => <span className="num">{r.metrics.sharpe.toFixed(2)}</span>,
    },
    {
      title: "最大回撤",
      key: "dd",
      align: "right",
      render: (_, r) => <span className="num down">{(r.metrics.max_drawdown * 100).toFixed(2)}%</span>,
    },
    {
      title: "胜率",
      key: "wr",
      align: "right",
      render: (_, r) => <span className="num">{(r.metrics.win_rate * 100).toFixed(1)}%</span>,
    },
    {
      title: "交易数",
      key: "tc",
      align: "right",
      render: (_, r) => <span className="num">{r.metrics.trade_count}</span>,
    },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-auto">
      <Card size="small" title="参数寻优（网格扫参 · 各参数 [起始, 结束, 步长] 生成组合）">
        <Space wrap className="mb-2">
          <Select
            placeholder="策略"
            options={classOptions}
            value={cls}
            onChange={setCls}
            style={{ width: 180 }}
          />
          <Select
            showSearch
            placeholder="标的"
            options={symbolOptions}
            value={symbol}
            onChange={setSymbol}
            filterOption={(i, o) => ((o?.label as string) ?? "").toLowerCase().includes(i.toLowerCase())}
            style={{ width: 180 }}
          />
          <RangePicker value={range} onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)} />
          <Select options={TARGETS} value={target} onChange={setTarget} style={{ width: 130 }} />
          <PermButton perm="backtest.run" type="primary" loading={submitting} onClick={runSweep}>
            开始寻优
          </PermButton>
        </Space>

        {schema && Object.keys(schema).length > 0 ? (
          <div className="flex flex-col gap-1">
            {Object.entries(schema).map(([name, def]) => {
              const r = ranges[name] ?? { min: 0, max: 0, step: 1 };
              const upd = (patch: Partial<Range>) =>
                setRanges((p) => ({ ...p, [name]: { ...r, ...patch } }));
              return (
                <div key={name} className="flex items-center gap-2 text-sm">
                  <span className="w-24 text-slate-500">{def.title}</span>
                  <InputNumber
                    size="small"
                    addonBefore="起"
                    value={r.min}
                    min={def.minimum ?? undefined}
                    max={def.maximum ?? undefined}
                    onChange={(v) => upd({ min: v ?? 0 })}
                  />
                  <InputNumber
                    size="small"
                    addonBefore="止"
                    value={r.max}
                    min={def.minimum ?? undefined}
                    max={def.maximum ?? undefined}
                    onChange={(v) => upd({ max: v ?? 0 })}
                  />
                  <InputNumber
                    size="small"
                    addonBefore="步"
                    value={r.step}
                    min={def.type.includes("int") ? 1 : 0.01}
                    onChange={(v) => upd({ step: v ?? 1 })}
                  />
                  <span className="text-xs text-slate-400">{buildList(r).length} 值</span>
                </div>
              );
            })}
            <div className="text-xs text-slate-400 mt-1">
              共 <span className={comboCount > MAX_COMBOS ? "text-red-500" : ""}>{comboCount}</span> 组合（上限 {MAX_COMBOS}）
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-400">选择策略后配置参数范围</div>
        )}
      </Card>

      {!jobId ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
          <Empty description="配置参数范围后开始寻优" />
        </Card>
      ) : status?.status === "failed" ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-red-500" }}>
          寻优失败：{status.error}
        </Card>
      ) : !result ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-slate-400 gap-2" }}>
          <Spin />
          <span>寻优计算中…（需 Celery worker 处理）</span>
        </Card>
      ) : (
        <>
          {result.best && (
            <Card size="small" title="最优参数">
              <Space size="large" wrap>
                <span className="num text-[var(--tc-primary)] font-medium">
                  {Object.entries(result.best.params).map(([k, v]) => `${k}=${v}`).join("  ")}
                </span>
                <span>夏普 <b className="num">{result.best.metrics.sharpe.toFixed(2)}</b></span>
                <span>
                  总收益{" "}
                  <b className={`num ${result.best.metrics.total_return >= 0 ? "up" : "down"}`}>
                    {(result.best.metrics.total_return * 100).toFixed(2)}%
                  </b>
                </span>
                <span>回撤 <b className="num down">{(result.best.metrics.max_drawdown * 100).toFixed(2)}%</b></span>
              </Space>
            </Card>
          )}
          {heatOption && (
            <Card size="small" title={`热力图（${result.param_keys.join(" × ")} → ${target}）`}>
              <ReactECharts option={heatOption} style={{ height: 300 }} notMerge />
            </Card>
          )}
          <Card size="small" title={`全部组合（${result.count}，按 ${target} 降序）`}>
            <Table<SweepResultRow>
              rowKey={(r) => JSON.stringify(r.params)}
              size="small"
              dataSource={rows}
              columns={cols}
              pagination={{ pageSize: 8 }}
            />
          </Card>
        </>
      )}
    </div>
  );
}
