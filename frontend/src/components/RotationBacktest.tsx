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
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { getBacktestStatus, getBacktestTrades, submitBacktest } from "@/api/backtest";
import { PermButton } from "@/components/PermButton";
import { EquityChart } from "@/components/EquityChart";
import { BacktestAnalysis } from "@/components/BacktestAnalysis";
import { TradeAnalysis } from "@/components/TradeAnalysis";
import type { BacktestStatus, BacktestTrade, RotationHolding } from "@/types";

const { RangePicker } = DatePicker;

const BENCHMARK_OPTIONS = [
  { value: "000300", label: "沪深300" },
  { value: "000905", label: "中证500" },
  { value: "399006", label: "创业板指" },
  { value: "000016", label: "上证50" },
];

function StatCard({ label, value, suffix = "" }: { label: string; value: string | number; suffix?: string }) {
  return (
    <Card size="small" className="text-center">
      <Statistic title={label} value={value} suffix={suffix} valueStyle={{ fontSize: 16 }} />
    </Card>
  );
}

/**
 * 多标的动量轮动回测：选 ≥2 标的 → 每 rebalance_days 个交易日按过去 lookback 日
 * 收益率排名，全仓持有最强者（动量全负则空仓）。复用 /backtest 接口，
 * class_name=RotationBacktest，标的列表与轮动参数走 params JSON。
 */
export function RotationBacktest({
  symbolOptions,
}: {
  symbolOptions: { value: string; label: string }[];
}) {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [lookback, setLookback] = useState(60);
  const [rebalanceDays, setRebalanceDays] = useState(20);
  const [initCapital, setInitCapital] = useState(1_000_000);
  const [benchmark, setBenchmark] = useState("000300");
  const [jobId, setJobId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["backtest", "rotation", jobId],
    queryFn: () => getBacktestStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (q: { state: { data?: BacktestStatus } }) => {
      const s = q.state.data?.status;
      return s === "done" || s === "failed" ? false : 2000;
    },
  });

  const { data: trades = [] } = useQuery({
    queryKey: ["backtest", "rotation", jobId, "trades"],
    queryFn: () => getBacktestTrades(jobId!),
    enabled: !!jobId && status?.status === "done",
  });

  const run = async () => {
    if (symbols.length < 2 || !range) {
      message.warning("请选择至少 2 个标的和回测区间");
      return;
    }
    setSubmitting(true);
    setJobId(null);
    try {
      const res = await submitBacktest({
        name: `轮动_${symbols.length}标的`,
        class_name: "RotationBacktest",
        symbol: symbols[0],
        params: { symbols, lookback, rebalance_days: rebalanceDays },
        start_date: range[0].format("YYYY-MM-DD"),
        end_date: range[1].format("YYYY-MM-DD"),
        init_capital: initCapital,
        commission_rate: 0.0003,
        slippage: 0.01,
        benchmark,
      });
      setJobId(res.job_id);
      message.success("轮动回测已提交，计算中…");
    } finally {
      setSubmitting(false);
    }
  };

  const result = status?.result ?? null;
  const holdings = result?.rotation_holdings ?? [];

  const holdingCols: ColumnsType<RotationHolding> = [
    { title: "调仓日", dataIndex: "dt", width: 110 },
    {
      title: "持有标的",
      dataIndex: "symbol",
      render: (s: string) =>
        s ? <Tag color="blue">{s}</Tag> : <Tag>空仓（动量全负）</Tag>,
    },
  ];

  const tradeCols: ColumnsType<BacktestTrade> = [
    { title: "时间", dataIndex: "dt", render: (v) => v.slice(0, 10), width: 100 },
    { title: "标的", dataIndex: "symbol", width: 100 },
    {
      title: "方向",
      dataIndex: "direction",
      width: 60,
      render: (_, r) => (
        <Tag color={r.offset === "open" ? "red" : "green"}>
          {r.offset === "open" ? "买入" : "卖出"}
        </Tag>
      ),
    },
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
      <Card size="small" title="动量轮动（每 N 个交易日持有过去 M 日最强标的，动量全负空仓）">
        <Space wrap>
          <Select
            mode="multiple"
            showSearch
            placeholder="标的池（≥2 个）"
            options={symbolOptions}
            value={symbols}
            onChange={setSymbols}
            filterOption={(i, o) => ((o?.label as string) ?? "").toLowerCase().includes(i.toLowerCase())}
            style={{ minWidth: 320 }}
            maxTagCount={4}
          />
          <RangePicker value={range} onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)} />
          <InputNumber addonBefore="动量窗口" value={lookback} min={5} max={250} onChange={(v) => setLookback(v ?? 60)} style={{ width: 170 }} />
          <InputNumber addonBefore="调仓间隔" value={rebalanceDays} min={1} max={120} onChange={(v) => setRebalanceDays(v ?? 20)} style={{ width: 170 }} />
          <InputNumber addonBefore="初始资金" value={initCapital} min={10000} step={100000} onChange={(v) => setInitCapital(v ?? 1_000_000)} style={{ width: 200 }} />
          <Select options={BENCHMARK_OPTIONS} value={benchmark} onChange={setBenchmark} style={{ width: 120 }} />
          <PermButton perm="backtest.run" type="primary" loading={submitting} onClick={run}>
            开始轮动回测
          </PermButton>
        </Space>
      </Card>

      {!jobId ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
          <Empty description="选择标的池后开始轮动回测" />
        </Card>
      ) : status?.status === "failed" ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-red-500" }}>
          回测失败：{status.error}
        </Card>
      ) : !result ? (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center text-slate-400 gap-2" }}>
          <Spin />
          <span>轮动计算中…（需 Celery worker 处理）</span>
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
              <StatCard label="调仓次数" value={holdings.length} />
            </Col>
            <Col span={4}>
              {result.excess_return != null ? (
                <StatCard label="超额收益" value={(result.excess_return * 100).toFixed(2)} suffix="%" />
              ) : (
                <StatCard label="交易次数" value={result.trade_count} />
              )}
            </Col>
          </Row>

          <Card title="资金曲线 + 回撤" size="small">
            <EquityChart result={result} trades={trades} />
          </Card>

          <Row gutter={[12, 12]}>
            <Col xs={24} lg={8}>
              <Card title="调仓时间线" size="small">
                <Table<RotationHolding>
                  dataSource={holdings}
                  columns={holdingCols}
                  rowKey="dt"
                  size="small"
                  pagination={{ pageSize: 8 }}
                />
              </Card>
            </Col>
            <Col xs={24} lg={16}>
              <Card title="成交明细" size="small">
                <Table<BacktestTrade>
                  dataSource={trades}
                  columns={tradeCols}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 8 }}
                />
              </Card>
            </Col>
          </Row>

          <BacktestAnalysis result={result} />
          <TradeAnalysis result={result} />
        </>
      )}
    </div>
  );
}
