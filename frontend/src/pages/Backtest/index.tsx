import { useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Drawer,
  Form,
  InputNumber,
  Row,
  Segmented,
  Select,
  Statistic,
  Table,
  Tag,
  message,
} from "antd";
import { ExperimentOutlined, RobotOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useSearchParams } from "react-router";
import { getBacktestStatus, getBacktestTrades, listBacktests, submitBacktest } from "@/api/backtest";
import { getSymbols } from "@/api/market";
import { getStrategyClasses } from "@/api/strategy";
import { streamBacktestAnalysis } from "@/api/ai";
import { StrategyParamsForm } from "@/components/StrategyParamsForm";
import { PageScaffold } from "@/components/PageScaffold";
import { PermButton } from "@/components/PermButton";
import { BacktestCompare } from "@/components/BacktestCompare";
import { ParamSweep } from "@/components/ParamSweep";
import { BacktestAnalysis } from "@/components/BacktestAnalysis";
import { TradeAnalysis } from "@/components/TradeAnalysis";
import { EquityChart } from "@/components/EquityChart";
import { RotationBacktest } from "@/components/RotationBacktest";
import { PairBacktest } from "@/components/PairBacktest";
import type { BacktestResult, BacktestStatus, BacktestTrade } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  pending: "default",
  running: "processing",
  done: "success",
  failed: "error",
};

// 对比基准指数（与后端 _BENCHMARK_INDICES 对齐）
const BENCHMARK_OPTIONS = [
  { value: "000300", label: "沪深300" },
  { value: "000905", label: "中证500" },
  { value: "399006", label: "创业板指" },
  { value: "000016", label: "上证50" },
];

function hasBenchmark(r: BacktestResult): boolean {
  return !!r.benchmark_curve && r.benchmark_curve.length > 0;
}

function MetricCard({ label, value, suffix = "" }: { label: string; value: string | number; suffix?: string }) {
  return (
    <Card size="small" className="text-center">
      <Statistic title={label} value={value} suffix={suffix} valueStyle={{ fontSize: 18 }} />
    </Card>
  );
}


export default function Backtest() {
  const qc = useQueryClient();
  const [form] = Form.useForm();
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [mode, setMode] = useState<"single" | "compare" | "sweep" | "rotation" | "pair">("single");
  const [sp] = useSearchParams();

  // 选股页「去回测」跳转：预填 symbol
  useEffect(() => {
    const s = sp.get("symbol");
    if (s) form.setFieldsValue({ symbol: s });
  }, [sp, form]);

  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    queryKey: ["backtest", "list"],
    queryFn: listBacktests,
  });

  const { data: selectedJob } = useQuery({
    queryKey: ["backtest", selectedJobId],
    queryFn: () => getBacktestStatus(selectedJobId!),
    enabled: !!selectedJobId,
    refetchInterval: pollingEnabled ? 2000 : false,
  });

  const { data: trades = [] } = useQuery({
    queryKey: ["backtest", selectedJobId, "trades"],
    queryFn: () => getBacktestTrades(selectedJobId!),
    enabled: !!selectedJobId && selectedJob?.status === "done",
  });

  // 停止轮询当完成
  useEffect(() => {
    if (selectedJob?.status === "done" || selectedJob?.status === "failed") {
      setPollingEnabled(false);
      qc.invalidateQueries({ queryKey: ["backtest", "list"] });
    }
  }, [selectedJob?.status, qc]);

  const { data: symbolsResp } = useQuery({
    queryKey: ["symbols", { limit: 200 }],
    queryFn: () => getSymbols({ limit: 200 }),
  });

  const { data: classes = [] } = useQuery({
    queryKey: ["strategy", "classes"],
    queryFn: getStrategyClasses,
  });
  const classOptions = classes.map((c) => ({ value: c.class_name, label: c.class_name }));
  const watchedClass = Form.useWatch("class_name", form);
  const selectedSchema = classes.find((c) => c.class_name === watchedClass)?.params_schema;

  const submitMut = useMutation({
    mutationFn: submitBacktest,
    onSuccess: (data) => {
      message.success("回测已提交，计算中…");
      setSelectedJobId(data.job_id);
      setPollingEnabled(true);
      qc.invalidateQueries({ queryKey: ["backtest", "list"] });
    },
  });

  function onFinish(values: Record<string, unknown>) {
    const start = values.start_date as dayjs.Dayjs;
    const end = values.end_date as dayjs.Dayjs;
    submitMut.mutate({
      name: values.name as string ?? `回测_${dayjs().format("MMDD_HHmm")}`,
      class_name: values.class_name as string,
      symbol: values.symbol as string,
      params: (values.params as Record<string, unknown>) ?? {},
      start_date: start.format("YYYY-MM-DD"),
      end_date: end.format("YYYY-MM-DD"),
      init_capital: values.init_capital as number ?? 1000000,
      commission_rate: (values.commission_rate as number ?? 0.03) / 100,
      slippage: values.slippage as number ?? 0.01,
      benchmark: (values.benchmark as string) ?? "000300",
    });
  }

  const symbolOptions = (symbolsResp?.items ?? []).map((s) => ({
    value: s.symbol,
    label: `${s.code} ${s.name}`,
  }));

  const jobColumns: ColumnsType<BacktestStatus> = [
    { title: "ID", dataIndex: "job_id", key: "job_id", width: 60 },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
    },
    {
      title: "收益率",
      key: "return",
      width: 90,
      render: (_, r) => {
        const ret = r.result?.total_return;
        if (ret == null) return "-";
        return (
          <span className={ret >= 0 ? "text-red-500" : "text-green-500"}>
            {(ret * 100).toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: "操作",
      key: "actions",
      render: (_, r) => (
        <Button size="small" type="link" onClick={() => {
          setSelectedJobId(r.job_id);
          if (r.status === "running" || r.status === "pending") setPollingEnabled(true);
        }}>
          查看
        </Button>
      ),
    },
  ];

  const tradeColumns: ColumnsType<BacktestTrade> = [
    { title: "时间", dataIndex: "dt", key: "dt", render: (v) => v.slice(0, 10), width: 100 },
    {
      title: "方向",
      dataIndex: "direction",
      width: 60,
      render: (v, r) => (
        <Tag color={r.offset === "open" ? (v === "long" ? "red" : "green") : "default"}>
          {r.offset === "open" ? (v === "long" ? "买入" : "卖空") : (v === "long" ? "卖出" : "平空")}
        </Tag>
      ),
    },
    { title: "价格", dataIndex: "price", key: "price", render: (v) => v.toFixed(2) },
    { title: "数量", dataIndex: "volume", key: "volume" },
    {
      title: "盈亏",
      dataIndex: "pnl",
      key: "pnl",
      render: (v) => v != null ? (
        <span className={v >= 0 ? "text-red-500" : "text-green-500"}>{v.toFixed(2)}</span>
      ) : "-",
    },
  ];

  const result = selectedJob?.result as BacktestResult | null;

  // ── AI 回测归因（SSE 流式）──
  const aiAbort = useRef<AbortController | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiStreaming, setAiStreaming] = useState(false);

  function openAiAnalysis() {
    if (!selectedJobId) return;
    aiAbort.current?.abort();
    const ctrl = new AbortController();
    aiAbort.current = ctrl;
    setAiOpen(true);
    setAiText("");
    setAiStreaming(true);
    void streamBacktestAnalysis(selectedJobId, {
      signal: ctrl.signal,
      onChunk: (t) => setAiText((p) => p + t),
      onDone: () => setAiStreaming(false),
      onError: (m) => {
        setAiText((p) => p + `\n\n⚠️ ${m}`);
        setAiStreaming(false);
      },
    });
  }

  return (
    <PageScaffold>
      <Segmented
        value={mode}
        onChange={(v) => setMode(v as "single" | "compare" | "sweep" | "rotation" | "pair")}
        options={[
          { label: "单次回测", value: "single" },
          { label: "策略对比", value: "compare" },
          { label: "参数寻优", value: "sweep" },
          { label: "轮动回测", value: "rotation" },
          { label: "配对交易", value: "pair" },
        ]}
        className="self-start"
      />
      {mode === "compare" ? (
        <BacktestCompare symbolOptions={symbolOptions} />
      ) : mode === "sweep" ? (
        <ParamSweep symbolOptions={symbolOptions} />
      ) : mode === "rotation" ? (
        <RotationBacktest symbolOptions={symbolOptions} />
      ) : mode === "pair" ? (
        <PairBacktest symbolOptions={symbolOptions} />
      ) : (
      <Row gutter={[16, 16]} className="flex-1 min-h-0">
        {/* 左：提交表单 */}
        <Col xs={24} lg={8} className="flex flex-col gap-4">
          <Card title="提交回测" size="small">
            <Form form={form} layout="vertical" onFinish={onFinish} size="small">
              <Form.Item label="策略类" name="class_name" rules={[{ required: true }]}>
                <Select options={classOptions} placeholder="选择策略" />
              </Form.Item>
              <Form.Item label="标的" name="symbol" rules={[{ required: true }]}>
                <Select
                  showSearch
                  options={symbolOptions}
                  filterOption={(input, opt) =>
                    (opt?.label ?? "").toLowerCase().includes(input.toLowerCase())
                  }
                  placeholder="搜索股票"
                />
              </Form.Item>
              <StrategyParamsForm schema={selectedSchema} />
              <Form.Item label="开始日期" name="start_date" rules={[{ required: true }]}>
                <DatePicker className="!w-full" />
              </Form.Item>
              <Form.Item label="结束日期" name="end_date" rules={[{ required: true }]}>
                <DatePicker className="!w-full" />
              </Form.Item>
              <Form.Item label="初始资金" name="init_capital" initialValue={1000000}>
                <InputNumber min={10000} step={100000} className="!w-full" />
              </Form.Item>
              <Form.Item label="对比基准" name="benchmark" initialValue="000300">
                <Select options={BENCHMARK_OPTIONS} />
              </Form.Item>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="手续费%" name="commission_rate" initialValue={0.03}>
                    <InputNumber min={0} max={1} step={0.01} className="!w-full" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="滑点" name="slippage" initialValue={0.01}>
                    <InputNumber min={0} step={0.01} className="!w-full" />
                  </Form.Item>
                </Col>
              </Row>
              <PermButton
                perm="backtest.run"
                type="primary"
                htmlType="submit"
                loading={submitMut.isPending}
                icon={<ExperimentOutlined />}
                block
              >
                开始回测
              </PermButton>
            </Form>
          </Card>

          <Card
            title="历史回测"
            size="small"
            loading={jobsLoading}
            className="flex-1"
            classNames={{ body: "flex-1 flex flex-col min-h-0" }}
          >
            <Table<BacktestStatus>
              dataSource={jobs}
              columns={jobColumns}
              rowKey="job_id"
              size="small"
              pagination={{ pageSize: 5 }}
              rowClassName={(r) => r.job_id === selectedJobId ? "!bg-blue-50" : ""}
              className="flex-1"
            />
          </Card>
        </Col>

        {/* 右：结果展示 */}
        <Col xs={24} lg={16} className="flex flex-col">
          {selectedJob?.status === "running" || selectedJob?.status === "pending" ? (
            <Card
              className="flex-1"
              classNames={{
                body: "flex-1 flex items-center justify-center gap-3 text-blue-500",
              }}
            >
              <span className="animate-spin text-2xl">⏳</span>
              <span>回测计算中，请稍候…（自动刷新）</span>
            </Card>
          ) : selectedJob?.status === "failed" ? (
            <Card
              className="flex-1"
              classNames={{
                body: "flex-1 flex flex-col items-center justify-center text-red-500 text-center",
              }}
            >
              <p className="font-bold text-lg mb-2">回测失败</p>
              <p className="text-sm">{selectedJob.error}</p>
            </Card>
          ) : result ? (
            <div className="flex-1 flex flex-col gap-4 min-h-0">
              <div className="flex justify-end">
                <PermButton perm="ai.chat" icon={<RobotOutlined />} onClick={openAiAnalysis}>
                  AI 归因
                </PermButton>
              </div>
              <Row gutter={[8, 8]}>
                <Col span={8}>
                  <MetricCard
                    label="总收益率"
                    value={(result.total_return * 100).toFixed(2)}
                    suffix="%"
                  />
                </Col>
                <Col span={8}>
                  <MetricCard
                    label="年化收益"
                    value={(result.annual_return * 100).toFixed(2)}
                    suffix="%"
                  />
                </Col>
                <Col span={8}>
                  <MetricCard label="夏普比率" value={result.sharpe.toFixed(3)} />
                </Col>
                <Col span={8}>
                  <MetricCard
                    label="最大回撤"
                    value={(result.max_drawdown * 100).toFixed(2)}
                    suffix="%"
                  />
                </Col>
                <Col span={8}>
                  <MetricCard
                    label="胜率"
                    value={(result.win_rate * 100).toFixed(1)}
                    suffix="%"
                  />
                </Col>
                <Col span={8}>
                  <MetricCard label="交易次数" value={result.trade_count} />
                </Col>
                {hasBenchmark(result) && (
                  <>
                    <Col span={8}>
                      <MetricCard
                        label="超额收益"
                        value={((result.excess_return ?? 0) * 100).toFixed(2)}
                        suffix="%"
                      />
                    </Col>
                    <Col span={8}>
                      <MetricCard
                        label="Alpha(年化)"
                        value={((result.alpha ?? 0) * 100).toFixed(2)}
                        suffix="%"
                      />
                    </Col>
                    <Col span={8}>
                      <MetricCard label="Beta" value={(result.beta ?? 0).toFixed(3)} />
                    </Col>
                  </>
                )}
              </Row>

              <Card
                title={
                  <span>
                    资金曲线 + 回撤
                    <span className="ml-3 text-xs text-slate-400">
                      <span className="inline-block w-2 h-2 bg-red-500 rounded mr-1" />
                      买入
                      <span className="inline-block w-2 h-2 bg-green-500 rounded ml-3 mr-1" />
                      卖出
                    </span>
                  </span>
                }
                size="small"
              >
                <EquityChart result={result} trades={trades} />
              </Card>

              <BacktestAnalysis result={result} />

              <TradeAnalysis result={result} />

              <Card title="成交明细" size="small">
                <Table<BacktestTrade>
                  dataSource={trades}
                  columns={tradeColumns}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 8 }}
                />
              </Card>
            </div>
          ) : (
            <Card
              className="flex-1"
              classNames={{
                body: "flex-1 flex flex-col items-center justify-center text-slate-400 text-center",
              }}
            >
              <ExperimentOutlined className="text-4xl mb-3" />
              <p>提交回测后，结果将在此显示</p>
            </Card>
          )}
        </Col>
      </Row>
      )}

      <Drawer
        title={`AI 回测归因 #${selectedJobId ?? ""}`}
        open={aiOpen}
        width={480}
        onClose={() => {
          aiAbort.current?.abort();
          setAiOpen(false);
        }}
      >
        {aiText ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{aiText}</div>
        ) : (
          <div className="text-slate-400">正在生成归因…</div>
        )}
        {aiStreaming && <span className="ml-1 animate-pulse text-blue-500">▋</span>}
      </Drawer>
    </PageScaffold>
  );
}
