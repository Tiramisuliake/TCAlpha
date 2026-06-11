import { useState } from "react";
import {
  Card,
  Col,
  DatePicker,
  Empty,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  message,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { getBacktestStatus, getBacktestTrades, submitBacktest } from "@/api/backtest";
import { PermButton } from "@/components/PermButton";
import { EquityChart } from "@/components/EquityChart";
import { BacktestAnalysis } from "@/components/BacktestAnalysis";
import { TradeAnalysis } from "@/components/TradeAnalysis";
import type { BacktestResult, BacktestStatus, BacktestTrade } from "@/types";

const { RangePicker } = DatePicker;

function StatCard({ label, value, suffix = "" }: { label: string; value: string | number; suffix?: string }) {
  return (
    <Card size="small" className="text-center">
      <Statistic title={label} value={value} suffix={suffix} valueStyle={{ fontSize: 16 }} />
    </Card>
  );
}

/** 成交动作标签：开/平 × 多/空 → 买入 / 卖空 / 卖出 / 买回。 */
function actionTag(t: BacktestTrade) {
  if (t.offset === "open") {
    return t.direction === "long"
      ? <Tag color="red">买入</Tag>
      : <Tag color="purple">卖空</Tag>;
  }
  return t.direction === "long"
    ? <Tag color="green">卖出</Tag>
    : <Tag color="cyan">买回</Tag>;
}

function ZScoreChart({ result }: { result: BacktestResult }) {
  const zs = result.pair_zscore ?? [];
  const entryZ = result.pair_entry_z ?? 2;
  const exitZ = result.pair_exit_z ?? 0.5;

  const option = {
    tooltip: { trigger: "axis" },
    grid: { left: 44, right: 16, top: 16, bottom: 40 },
    xAxis: {
      type: "category",
      data: zs.map((p) => p.dt),
      axisLabel: { fontSize: 10, rotate: 30 },
    },
    yAxis: { type: "value", name: "z", scale: true },
    series: [
      {
        name: "z-score",
        type: "line",
        data: zs.map((p) => p.value),
        symbol: "none",
        smooth: true,
        lineStyle: { color: "#8b5cf6", width: 1.5 },
        markLine: {
          silent: true,
          symbol: "none",
          data: [
            { yAxis: entryZ, lineStyle: { color: "#ef4444", type: "dashed" }, label: { formatter: `开仓 +${entryZ}`, fontSize: 10 } },
            { yAxis: -entryZ, lineStyle: { color: "#ef4444", type: "dashed" }, label: { formatter: `开仓 -${entryZ}`, fontSize: 10 } },
            { yAxis: exitZ, lineStyle: { color: "#94a3b8", type: "dotted" }, label: { formatter: `平仓 ±${exitZ}`, fontSize: 10 } },
            { yAxis: -exitZ, lineStyle: { color: "#94a3b8", type: "dotted" }, label: { show: false } },
          ],
        },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 240 }} notMerge />;
}

/**
 * 配对交易回测（统计套利）：价差 z-score 均值回归，z 突破 ±entry_z 开仓
 * （多弱空强各半仓），|z| < exit_z 平仓。复用 /backtest 接口，
 * class_name=PairTradingBacktest，A/B 标的与参数走 params JSON。
 * 做空为模拟语义（融券简化），实盘券源/保证金不建模。
 */
export function PairBacktest({
  symbolOptions,
}: {
  symbolOptions: { value: string; label: string }[];
}) {
  const [symbolA, setSymbolA] = useState<string>();
  const [symbolB, setSymbolB] = useState<string>();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [window, setWindow] = useState(60);
  const [entryZ, setEntryZ] = useState(2.0);
  const [exitZ, setExitZ] = useState(0.5);
  const [initCapital, setInitCapital] = useState(1_000_000);
  const [jobId, setJobId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["backtest", "pair", jobId],
    queryFn: () => getBacktestStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (q: { state: { data?: BacktestStatus } }) => {
      const s = q.state.data?.status;
      return s === "done" || s === "failed" ? false : 2000;
    },
  });

  const { data: trades = [] } = useQuery({
    queryKey: ["backtest", "pair", jobId, "trades"],
    queryFn: () => getBacktestTrades(jobId!),
    enabled: !!jobId && status?.status === "done",
  });

  const run = async () => {
    if (!symbolA || !symbolB || !range) {
      message.warning("请选择 A / B 两个标的和回测区间");
      return;
    }
    if (symbolA === symbolB) {
      message.warning("A / B 标的不能相同");
      return;
    }
    setSubmitting(true);
    setJobId(null);
    try {
      const res = await submitBacktest({
        name: `配对_${symbolA}_${symbolB}`,
        class_name: "PairTradingBacktest",
        symbol: symbolA,
        params: { symbol_a: symbolA, symbol_b: symbolB, window, entry_z: entryZ, exit_z: exitZ },
        start_date: range[0].format("YYYY-MM-DD"),
        end_date: range[1].format("YYYY-MM-DD"),
        init_capital: initCapital,
        commission_rate: 0.0003,
        slippage: 0.01,
        benchmark: "000300",
      });
      setJobId(res.job_id);
      message.success("配对回测已提交，计算中…");
    } finally {
      setSubmitting(false);
    }
  };

  const result = status?.result ?? null;

  const tradeCols: ColumnsType<BacktestTrade> = [
    { title: "时间", dataIndex: "dt", render: (v) => v.slice(0, 10), width: 100 },
    { title: "标的", dataIndex: "symbol", width: 100 },
    { title: "动作", key: "action", width: 70, render: (_, r) => actionTag(r) },
    { title: "价格", dataIndex: "price", render: (v) => v.toFixed(2) },
    { title: "数量", dataIndex: "volume" },
    {
      title: "盈亏",
      dataIndex: "pnl",
      render: (v) => v != null ? (
        <span className={v >= 0 ? "text-red-500" : "text-green-500"}>{v.toFixed(2)}</span>
      ) : "-",
    },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-auto">
      <Card size="small" title="配对交易（价差 z-score 均值回归 · 多弱空强 · 做空为模拟语义）">
        <Space wrap>
          <Select
            showSearch
            placeholder="标的 A"
            options={symbolOptions}
            value={symbolA}
            onChange={setSymbolA}
            filterOption={(i, o) => ((o?.label as string) ?? "").toLowerCase().includes(i.toLowerCase())}
            style={{ width: 180 }}
          />
          <Select
            showSearch
            placeholder="标的 B"
            options={symbolOptions}
            value={symbolB}
            onChange={setSymbolB}
            filterOption={(i, o) => ((o?.label as string) ?? "").toLowerCase().includes(i.toLowerCase())}
            style={{ width: 180 }}
          />
          <RangePicker value={range} onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)} />
          <InputNumber addonBefore="z 窗口" value={window} min={10} max={250} onChange={(v) => setWindow(v ?? 60)} style={{ width: 150 }} />
          <InputNumber addonBefore="开仓 z" value={entryZ} min={0.5} max={5} step={0.1} onChange={(v) => setEntryZ(v ?? 2)} style={{ width: 150 }} />
          <InputNumber addonBefore="平仓 z" value={exitZ} min={0} max={2} step={0.1} onChange={(v) => setExitZ(v ?? 0.5)} style={{ width: 150 }} />
          <InputNumber addonBefore="初始资金" value={initCapital} min={10000} step={100000} onChange={(v) => setInitCapital(v ?? 1_000_000)} style={{ width: 200 }} />
          <PermButton perm="backtest.run" type="primary" loading={submitting} onClick={run}>
            开始配对回测
          </PermButton>
        </Space>
      </Card>

      {!jobId ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
          <Empty description="选择 A / B 标的后开始配对回测" />
        </Card>
      ) : status?.status === "failed" ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-red-500" }}>
          回测失败：{status.error}
        </Card>
      ) : !result ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-slate-400 gap-2" }}>
          <Spin />
          <span>配对计算中…（需 Celery worker 处理）</span>
        </Card>
      ) : (
        <>
          <Row gutter={[8, 8]}>
            <Col span={4}>
              <StatCard label="总收益率" value={(result.total_return * 100).toFixed(2)} suffix="%" />
            </Col>
            <Col span={4}>
              <StatCard label="年化收益" value={(result.annual_return * 100).toFixed(2)} suffix="%" />
            </Col>
            <Col span={4}>
              <StatCard label="夏普比率" value={result.sharpe.toFixed(3)} />
            </Col>
            <Col span={4}>
              <StatCard label="最大回撤" value={(result.max_drawdown * 100).toFixed(2)} suffix="%" />
            </Col>
            <Col span={4}>
              <StatCard label="平仓笔数" value={result.trade_count} />
            </Col>
            <Col span={4}>
              <StatCard label="胜率" value={(result.win_rate * 100).toFixed(1)} suffix="%" />
            </Col>
          </Row>

          <Card title="资金曲线 + 回撤" size="small">
            <EquityChart result={result} trades={trades} />
          </Card>

          <Card
            title={`价差 z-score（${(result.pair_symbols ?? []).join(" / ")} · 窗口 ${result.pair_window ?? "-"}）`}
            size="small"
          >
            <ZScoreChart result={result} />
          </Card>

          <Card title="成交明细（双腿）" size="small">
            <Table<BacktestTrade>
              dataSource={trades}
              columns={tradeCols}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 8 }}
            />
          </Card>

          <BacktestAnalysis result={result} />
          <TradeAnalysis result={result} />
        </>
      )}
    </div>
  );
}
