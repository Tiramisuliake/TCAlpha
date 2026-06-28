import { useState } from "react";
import type { Key, ReactNode } from "react";
import { Alert, Button, Card, Empty, InputNumber, Space, Switch, Table, Tooltip, message } from "antd";
import { ThunderboltOutlined, StarOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import type { ColumnsType } from "antd/es/table";
import { runFactorScreen } from "@/api/screener";
import { addWatch, addWatchBatch } from "@/api/watchlist";
import type { FactorWeights, ScreenCandidate } from "@/types";
import { DEFAULT_FACTOR_WEIGHTS, FACTORS } from "./factorMeta";

function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </div>
  );
}

function fmt(v: number | undefined, unit: string): ReactNode {
  if (v == null) return "-";
  if (unit === "pct") {
    const pct = v * 100;
    return <span className={`num ${pct >= 0 ? "up" : "down"}`}>{pct.toFixed(1)}%</span>;
  }
  if (unit === "x") return <span className="num">{v.toFixed(2)}×</span>;
  if (unit === "rsi") return <span className="num">{v.toFixed(1)}</span>;
  if (unit === "pctb") return <span className="num">{v.toFixed(2)}</span>;
  if (unit === "lo") return <span className="num text-slate-500">{v.toFixed(3)}</span>;
  return <span className={`num ${v >= 0 ? "up" : "down"}`}>{v.toFixed(3)}</span>;
}

/**
 * 时序多因子选股：从 ArcticDB 历史日 K 计算多周期动量 / 波动率 / 趋势斜率 / 量能因子，
 * 横截面 z-score 标准化后按方向加权综合打分排序。可配各因子权重调整选股风格。
 */
export default function FactorScreen() {
  const [weights, setWeights] = useState<FactorWeights>(DEFAULT_FACTOR_WEIGHTS);
  const [priceMin, setPriceMin] = useState<number | undefined>();
  const [priceMax, setPriceMax] = useState<number | undefined>();
  const [excludeSt, setExcludeSt] = useState(true);
  const [limit, setLimit] = useState(50);
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);

  const navigate = useNavigate();
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

  const mut = useMutation({
    mutationFn: runFactorScreen,
    onSuccess: (res) => {
      setSelectedKeys([]);
      if (!res.ready) message.info("尚无历史 K 线，请先到「数据」页下载日 K");
      else message.success(`综合打分 ${res.count} 只`);
    },
  });

  const setWeight = (key: keyof FactorWeights, v: number) =>
    setWeights((p) => ({ ...p, [key]: v }));

  const scan = () =>
    mut.mutate({ weights, price_min: priceMin, price_max: priceMax, exclude_st: excludeSt, limit });

  const result = mut.data;
  const candidates = result?.candidates ?? [];

  const cols: ColumnsType<ScreenCandidate> = [
    { title: "代码", dataIndex: "code", width: 78, render: (v: string) => <span className="num">{v}</span> },
    { title: "名称", dataIndex: "name", width: 90 },
    {
      title: "最新价",
      dataIndex: "price",
      align: "right",
      render: (v: number | undefined) => (v != null ? <span className="num">{v.toFixed(2)}</span> : "-"),
    },
    ...FACTORS.map((f) => ({
      title: <Tooltip title={f.desc}>{f.label}</Tooltip>,
      dataIndex: f.key,
      align: "right" as const,
      render: (v: number | undefined) => fmt(v, f.unit),
    })),
    {
      title: "综合分",
      dataIndex: "score",
      align: "right" as const,
      defaultSortOrder: "descend" as const,
      sorter: (a: ScreenCandidate, b: ScreenCandidate) => (a.score ?? 0) - (b.score ?? 0),
      render: (v: number | undefined) =>
        v != null ? <span className="num font-medium text-blue-600">{v.toFixed(3)}</span> : "-",
    },
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
      <Card size="small" title="时序多因子选股（基于历史日 K 计算的连续因子，横截面 z-score 加权）">
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
          <Field label="股价 ≥">
            <InputNumber size="small" value={priceMin} onChange={(v) => setPriceMin(v ?? undefined)} />
          </Field>
          <Field label="股价 ≤">
            <InputNumber size="small" value={priceMax} onChange={(v) => setPriceMax(v ?? undefined)} />
          </Field>
          <Field label="排除 ST">
            <Switch size="small" checked={excludeSt} onChange={setExcludeSt} />
          </Field>
          <Field label="数量">
            <InputNumber size="small" min={1} max={200} value={limit} onChange={(v) => setLimit(v ?? 50)} />
          </Field>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={mut.isPending} onClick={scan}>
            综合打分
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          各因子在候选集内 z-score 标准化（按方向：动量/趋势/量能越高越优，波动率越低越优），按权重加权求综合分降序。权重置 0 即排除该因子。
        </div>
      </Card>

      {result && !result.ready && (
        <Alert type="info" showIcon message="尚无历史 K 线数据，请先到「数据」页批量下载日 K 后再打分" />
      )}

      <Card
        size="small"
        title={result?.ready ? `综合排名（${result.count} 只）` : "结果"}
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
        extra={
          candidates.length > 0 ? (
            <Space>
              <Tooltip title={result?.cached ? "因子值取自每日收盘快照缓存（秒级返回）" : "缓存未命中，本次实时全市场计算"}>
                <span className="text-xs text-slate-400">
                  {result?.cached ? `📦 因子快照 ${result.as_of ?? ""}` : "⚡ 实时计算"}
                </span>
              </Tooltip>
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
            </Space>
          ) : null
        }
      >
        {candidates.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <Empty description="设置权重后点「综合打分」" />
          </div>
        ) : (
          <Table<ScreenCandidate>
            rowKey="symbol"
            size="small"
            dataSource={candidates}
            columns={cols}
            rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
            pagination={{ pageSize: 15 }}
            scroll={{ x: 1180 }}
            className="flex-1"
          />
        )}
      </Card>
    </>
  );
}
