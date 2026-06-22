import { useState } from "react";
import type { ReactNode } from "react";
import type { Key } from "react";
import { Alert, Button, Card, Empty, InputNumber, Select, Space, Switch, Table, Tag, message } from "antd";
import { ThunderboltOutlined, StarOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import type { ColumnsType } from "antd/es/table";
import { runPatternStats, runResonance, runShortTerm } from "@/api/screener";
import { addWatch, addWatchBatch } from "@/api/watchlist";
import type { ScreenCandidate, ShortTermFilters } from "@/types";

const PATTERN_OPTIONS = [
  { value: "volume_breakout", label: "放量突破" },
  { value: "ma_long", label: "均线多头" },
  { value: "pullback", label: "回踩企稳" },
  { value: "limit_up", label: "涨停打板" },
  { value: "resonance", label: "多形态共振" },
];

const PATTERN_DESC: Record<string, string> = {
  volume_breakout: "收盘突破前 N 日新高 + 当日放量确认（量比 ≥ 阈值）——短线启动信号",
  ma_long: "MA5 > MA10 > MA20 且收盘站上 MA5——强势多头排列，趋势延续",
  pullback: "上升趋势中当日最低回踩 MA10 并收回其上——短线低吸点",
  limit_up: "尾部连续涨停（按板块涨停价判定），按连板高度排序——打板情绪龙头",
  resonance: "同时命中多个独立形态（如放量突破 + 均线多头）——多形态共振强信号，按命中数排序",
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </div>
  );
}

/**
 * 短线技术选股：基于 ArcticDB 历史日 K 的量价形态扫描（放量突破 / 均线多头 / 回踩企稳），
 * 命中后按短线动能（量比 + 近 5 日涨幅 + 距新高接近度）打分排序。
 * 与基本面截面筛选互补，面向短线交易买点。
 */
export default function ShortTerm() {
  const [filters, setFilters] = useState<ShortTermFilters>({
    pattern: "volume_breakout",
    breakout_window: 20,
    vol_ratio_min: 1.5,
    min_boards: 1,
    exclude_st: true,
    limit: 50,
  });
  const [minPatterns, setMinPatterns] = useState(2);
  const set = (patch: Partial<ShortTermFilters>) => setFilters((p) => ({ ...p, ...patch }));
  const isResonance = filters.pattern === "resonance";

  const navigate = useNavigate();
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);
  const addMut = useMutation({
    mutationFn: (symbol: string) => addWatch(symbol),
    onSuccess: () => message.success("已加入自选"),
  });
  const batchMut = useMutation({
    mutationFn: (symbols: string[]) => addWatchBatch(symbols),
    onSuccess: (res) => {
      const parts = [`已加 ${res.added.length} 只`];
      if (res.skipped.length) parts.push(`跳过 ${res.skipped.length} 只（已在自选）`);
      if (res.failed.length) parts.push(`失败 ${res.failed.length} 只`);
      const text = parts.join("，");
      if (res.failed.length) message.warning(text);
      else message.success(text);
      setSelectedKeys([]);
    },
  });

  const onScanSuccess = (res: { ready: boolean; count: number }) => {
    setSelectedKeys([]);
    if (!res.ready) message.info("尚无历史 K 线，请先到「数据」页下载日 K");
    else message.success(`命中 ${res.count} 只`);
  };
  const mut = useMutation({ mutationFn: runShortTerm, onSuccess: onScanSuccess });
  const resMut = useMutation({ mutationFn: runResonance, onSuccess: onScanSuccess });

  // 形态有效性：当前形态全市场历史命中后持有 5 日的平均收益与胜率（共振模式不适用）
  const { data: stats } = useQuery({
    queryKey: ["pattern-stats", filters.pattern],
    queryFn: () => runPatternStats({ pattern: filters.pattern, hold_days: 5, lookback: 250 }),
    enabled: !isResonance,
    staleTime: 5 * 60_000,
  });

  const scan = () =>
    isResonance
      ? resMut.mutate({ min_patterns: minPatterns, exclude_st: filters.exclude_st, limit: filters.limit })
      : mut.mutate(filters);
  const scanning = isResonance ? resMut.isPending : mut.isPending;
  const result = isResonance ? resMut.data : mut.data;
  const candidates = result?.candidates ?? [];

  const cols: ColumnsType<ScreenCandidate> = [
    { title: "代码", dataIndex: "code", width: 80, render: (v: string) => <span className="num">{v}</span> },
    { title: "名称", dataIndex: "name", width: 100 },
    {
      title: "最新价",
      dataIndex: "price",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{v.toFixed(2)}</span> : "-"),
    },
    ...(isResonance
      ? ([
          {
            title: "命中形态",
            key: "patterns",
            render: (_: unknown, r: ScreenCandidate) => (
              <span className="flex flex-wrap gap-1">
                {(r.patterns ?? []).map((p) => (
                  <Tag key={p} color="red" className="!m-0">{p}</Tag>
                ))}
              </span>
            ),
          },
          {
            title: "共振数",
            dataIndex: "match_count",
            align: "right" as const,
            render: (v: number | null) =>
              v != null ? <span className="num font-medium text-blue-600">{v}</span> : "-",
          },
        ] as ColumnsType<ScreenCandidate>)
      : ([
          {
            title: "量比",
            dataIndex: "vol_ratio",
            align: "right" as const,
            render: (v: number | null) =>
              v != null ? <span className={`num ${v >= 1.5 ? "up" : ""}`}>{v.toFixed(2)}</span> : "-",
          },
          {
            title: "近5日涨幅",
            dataIndex: "ret5",
            align: "right" as const,
            render: (v: number | null) =>
              v != null ? <span className={`num ${v >= 0 ? "up" : "down"}`}>{(v * 100).toFixed(2)}%</span> : "-",
          },
          {
            title: "距新高",
            dataIndex: "dist_high",
            align: "right" as const,
            render: (v: number | null) => (v != null ? <span className="num">{(v * 100).toFixed(2)}%</span> : "-"),
          },
          {
            title: "均线",
            key: "ma",
            render: (_: unknown, r: ScreenCandidate) =>
              r.ma5 != null && r.ma10 != null && r.ma20 != null ? (
                r.ma5 > r.ma10 && r.ma10 > r.ma20 ? <Tag color="red">多头</Tag> : <Tag>纠缠</Tag>
              ) : (
                "-"
              ),
          },
          ...(filters.pattern === "limit_up"
            ? [{
                title: "连板",
                dataIndex: "boards",
                align: "right" as const,
                render: (v: number | null) =>
                  v != null && v > 0 ? <Tag color="red">{v} 板</Tag> : "-",
              }]
            : []),
          {
            title: "评分",
            dataIndex: "score",
            align: "right" as const,
            render: (v: number | null) =>
              v != null ? <span className="num font-medium text-blue-600">{v.toFixed(3)}</span> : "-",
          },
        ] as ColumnsType<ScreenCandidate>)),
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
    <>
      <Card size="small" title="短线技术选股（基于历史日 K 量价形态）">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <Field label="买点形态">
            <Select
              size="small"
              style={{ width: 130 }}
              options={PATTERN_OPTIONS}
              value={filters.pattern}
              onChange={(v) => set({ pattern: v })}
            />
          </Field>
          {isResonance ? (
            <Field label="最少形态数">
              <InputNumber size="small" min={2} max={4} value={minPatterns} onChange={(v) => setMinPatterns(v ?? 2)} />
            </Field>
          ) : (
            <>
              <Field label="突破窗口(日)">
                <InputNumber size="small" min={5} max={120} value={filters.breakout_window} onChange={(v) => set({ breakout_window: v ?? 20 })} />
              </Field>
              <Field label="量比 ≥（放量突破用）">
                <InputNumber size="small" min={1} step={0.1} value={filters.vol_ratio_min} onChange={(v) => set({ vol_ratio_min: v ?? 1.5 })} />
              </Field>
              {filters.pattern === "limit_up" && (
                <Field label="连板下限">
                  <InputNumber size="small" min={1} max={10} value={filters.min_boards ?? 1} onChange={(v) => set({ min_boards: v ?? 1 })} />
                </Field>
              )}
            </>
          )}
          <Field label="股价 ≥">
            <InputNumber size="small" value={filters.price_min} onChange={(v) => set({ price_min: v ?? undefined })} />
          </Field>
          <Field label="股价 ≤">
            <InputNumber size="small" value={filters.price_max} onChange={(v) => set({ price_max: v ?? undefined })} />
          </Field>
          <Field label="排除 ST">
            <Switch size="small" checked={filters.exclude_st} onChange={(v) => set({ exclude_st: v })} />
          </Field>
          <Field label="数量">
            <InputNumber size="small" min={1} max={200} value={filters.limit} onChange={(v) => set({ limit: v ?? 50 })} />
          </Field>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={scanning} onClick={scan}>
            扫描
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">{PATTERN_DESC[filters.pattern]}</div>
        {stats?.ready && stats.count > 0 && (
          <div className="mt-1 text-xs text-slate-500">
            形态有效性（全市场近 250 日，命中后持有 5 日）：命中{" "}
            <b className="num">{stats.count}</b> 次 · 平均收益{" "}
            <b className={stats.avg_return >= 0 ? "text-red-500" : "text-green-500"}>
              {(stats.avg_return * 100).toFixed(2)}%
            </b>{" "}
            · 胜率 <b className="num">{(stats.win_rate * 100).toFixed(1)}%</b>
          </div>
        )}
      </Card>

      {result && !result.ready && (
        <Alert type="info" showIcon message="尚无历史 K 线数据，请先到「数据」页批量下载日 K 后再扫描" />
      )}

      <Card
        size="small"
        title={result?.ready ? `命中（${result.count} 只）` : "结果"}
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
        extra={
          candidates.length > 0 ? (
            <Button
              size="small"
              type="primary"
              ghost
              icon={<StarOutlined />}
              disabled={selectedKeys.length === 0}
              loading={batchMut.isPending}
              onClick={() => batchMut.mutate(selectedKeys.map(String))}
            >
              批量加自选{selectedKeys.length ? `（${selectedKeys.length}）` : ""}
            </Button>
          ) : null
        }
      >
        {candidates.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description="选择形态后点「扫描」" />
          </div>
        ) : (
          <Table<ScreenCandidate>
            rowKey="symbol"
            size="small"
            dataSource={candidates}
            columns={cols}
            rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
            pagination={{ pageSize: 15 }}
            className="flex-1"
          />
        )}
      </Card>
    </>
  );
}
