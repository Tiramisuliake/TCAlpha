import { useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Card, Empty, InputNumber, Segmented, Select, Space, Switch, Table, message } from "antd";
import { FilterOutlined, StarOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import type { ColumnsType } from "antd/es/table";
import { runScreen } from "@/api/screener";
import { addWatch } from "@/api/watchlist";
import { PageScaffold } from "@/components/PageScaffold";
import ShortTerm from "./ShortTerm";
import LimitUpStats from "./LimitUpStats";
import FactorScreen from "./FactorScreen";
import FactorIC from "./FactorIC";
import FactorPortfolio from "./FactorPortfolio";
import type { ScreenCandidate, ScreenFilters } from "@/types";

type ScreenMode =
  | "fundamental"
  | "factor"
  | "factor_ic"
  | "factor_portfolio"
  | "short_term"
  | "board_review";

const SORT_OPTIONS = [
  { value: "amount", label: "成交额" },
  { value: "market_cap", label: "市值" },
  { value: "pct_chg", label: "涨跌幅" },
  { value: "turnover", label: "换手率" },
  { value: "pe", label: "市盈率" },
];

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </div>
  );
}

export default function Screener() {
  const [mode, setMode] = useState<ScreenMode>("fundamental");
  const [filters, setFilters] = useState<ScreenFilters>({
    exclude_st: true,
    sort_by: "amount",
    limit: 50,
  });
  const set = (patch: Partial<ScreenFilters>) => setFilters((p) => ({ ...p, ...patch }));

  const navigate = useNavigate();
  const addMut = useMutation({
    mutationFn: (symbol: string) => addWatch(symbol),
    onSuccess: () => message.success("已加入自选"),
  });

  const mut = useMutation({
    mutationFn: runScreen,
    onSuccess: (res) => {
      if (!res.ready) message.info("全市场快照刷新中，请几秒后重试");
      else message.success(`筛选出 ${res.count} 只`);
    },
  });

  const result = mut.data;
  const candidates = result?.candidates ?? [];

  const cols: ColumnsType<ScreenCandidate> = [
    { title: "代码", dataIndex: "code", key: "code", width: 80, render: (v: string) => <span className="num">{v}</span> },
    { title: "名称", dataIndex: "name", key: "name", width: 100 },
    {
      title: "最新价",
      dataIndex: "price",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{v.toFixed(2)}</span> : "-"),
    },
    {
      title: "涨跌幅",
      dataIndex: "pct_chg",
      align: "right",
      render: (v: number | null) =>
        v != null ? <span className={`num ${v >= 0 ? "up" : "down"}`}>{v.toFixed(2)}%</span> : "-",
    },
    {
      title: "总市值(亿)",
      dataIndex: "market_cap",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{(v / 1e8).toFixed(1)}</span> : "-"),
    },
    {
      title: "市盈率",
      dataIndex: "pe",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{v.toFixed(1)}</span> : "-"),
    },
    {
      title: "成交额(亿)",
      dataIndex: "amount",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{(v / 1e8).toFixed(2)}</span> : "-"),
    },
    {
      title: "换手%",
      dataIndex: "turnover",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{v.toFixed(2)}</span> : "-"),
    },
    ...(filters.factor_mode
      ? ([{
          title: "评分",
          dataIndex: "score",
          align: "right" as const,
          render: (v: number | null) =>
            v != null ? <span className="num font-medium text-blue-600">{v.toFixed(3)}</span> : "-",
        }] as ColumnsType<ScreenCandidate>)
      : []),
    {
      title: "操作",
      key: "actions",
      width: 180,
      render: (_: unknown, row: ScreenCandidate) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<StarOutlined />}
            loading={addMut.isPending && addMut.variables === row.symbol}
            onClick={() => addMut.mutate(row.symbol)}
          >
            自选
          </Button>
          <Button size="small" type="link" onClick={() => navigate(`/backtest?symbol=${row.symbol}`)}>
            回测
          </Button>
          <Button size="small" type="link" onClick={() => navigate(`/strategy?symbol=${row.symbol}`)}>
            建策略
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <PageScaffold>
      <Segmented
        value={mode}
        onChange={(v) => setMode(v as ScreenMode)}
        options={[
          { label: "基本面筛选", value: "fundamental" },
          { label: "多因子选股", value: "factor" },
          { label: "因子检验", value: "factor_ic" },
          { label: "组合回测", value: "factor_portfolio" },
          { label: "短线技术选股", value: "short_term" },
          { label: "打板复盘", value: "board_review" },
        ]}
        className="self-start"
      />
      {mode === "factor" ? (
        <FactorScreen />
      ) : mode === "factor_ic" ? (
        <FactorIC />
      ) : mode === "factor_portfolio" ? (
        <FactorPortfolio />
      ) : mode === "short_term" ? (
        <ShortTerm />
      ) : mode === "board_review" ? (
        <LimitUpStats />
      ) : (
      <>
      <Card size="small" title="选股条件（基于全市场实时快照）">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <Field label="市值(亿) ≥">
            <InputNumber size="small" value={filters.market_cap_min} onChange={(v) => set({ market_cap_min: v ?? undefined })} />
          </Field>
          <Field label="市值(亿) ≤">
            <InputNumber size="small" value={filters.market_cap_max} onChange={(v) => set({ market_cap_max: v ?? undefined })} />
          </Field>
          <Field label="PE ≥">
            <InputNumber size="small" value={filters.pe_min} onChange={(v) => set({ pe_min: v ?? undefined })} />
          </Field>
          <Field label="PE ≤">
            <InputNumber size="small" value={filters.pe_max} onChange={(v) => set({ pe_max: v ?? undefined })} />
          </Field>
          <Field label="成交额(亿) ≥">
            <InputNumber size="small" value={filters.amount_min} onChange={(v) => set({ amount_min: v ?? undefined })} />
          </Field>
          <Field label="换手% ≥">
            <InputNumber size="small" value={filters.turnover_min} onChange={(v) => set({ turnover_min: v ?? undefined })} />
          </Field>
          <Field label="涨幅% ≥">
            <InputNumber size="small" value={filters.pct_chg_min} onChange={(v) => set({ pct_chg_min: v ?? undefined })} />
          </Field>
          <Field label="涨幅% ≤">
            <InputNumber size="small" value={filters.pct_chg_max} onChange={(v) => set({ pct_chg_max: v ?? undefined })} />
          </Field>
          <Field label="排除 ST">
            <Switch size="small" checked={filters.exclude_st} onChange={(v) => set({ exclude_st: v })} />
          </Field>
          <Field label="多因子打分">
            <Switch size="small" checked={filters.factor_mode} onChange={(v) => set({ factor_mode: v })} />
          </Field>
          {filters.factor_mode && (
            <>
              <Field label="动量权重">
                <InputNumber size="small" min={0} step={0.5} value={filters.w_momentum ?? 1} onChange={(v) => set({ w_momentum: v ?? 1 })} />
              </Field>
              <Field label="估值权重">
                <InputNumber size="small" min={0} step={0.5} value={filters.w_value ?? 1} onChange={(v) => set({ w_value: v ?? 1 })} />
              </Field>
              <Field label="换手权重">
                <InputNumber size="small" min={0} step={0.5} value={filters.w_turnover ?? 1} onChange={(v) => set({ w_turnover: v ?? 1 })} />
              </Field>
            </>
          )}
          <Field label="排序">
            <Select size="small" style={{ width: 110 }} options={SORT_OPTIONS} value={filters.sort_by} onChange={(v) => set({ sort_by: v })} />
          </Field>
          <Field label="数量">
            <InputNumber size="small" min={1} max={200} value={filters.limit} onChange={(v) => set({ limit: v ?? 50 })} />
          </Field>
          <Button type="primary" icon={<FilterOutlined />} loading={mut.isPending} onClick={() => mut.mutate(filters)}>
            筛选
          </Button>
        </div>
      </Card>

      {result && !result.ready && (
        <Alert type="info" showIcon message="全市场快照刷新中（需 Celery worker 处理），请几秒后重新筛选" />
      )}

      <Card
        size="small"
        title={result?.ready ? `结果（${result.count} 只）` : "结果"}
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
      >
        {candidates.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description="设置条件后点「筛选」" />
          </div>
        ) : (
          <Table<ScreenCandidate>
            rowKey="symbol"
            size="small"
            dataSource={candidates}
            columns={cols}
            pagination={{ pageSize: 15 }}
            className="flex-1"
          />
        )}
      </Card>
      </>
      )}
    </PageScaffold>
  );
}
