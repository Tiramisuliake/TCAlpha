import { Badge, Card, Empty, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import { getBoard, type BoardItem } from "@/api/watchlist";
import { matchPatterns } from "@/api/screener";
import type { AlertLevel } from "@/api/ai_alerts";
import { PageScaffold } from "@/components/PageScaffold";

const LEVEL_COLOR: Record<AlertLevel, string> = {
  info: "blue",
  warn: "orange",
  danger: "red",
};

// 短线形态标签配色（与选股形态对齐）
const PATTERN_COLOR: Record<string, string> = {
  放量突破: "red",
  均线多头: "volcano",
  回踩企稳: "blue",
  涨停打板: "magenta",
};

export default function Monitor() {
  const { data, isLoading } = useQuery({
    queryKey: ["watchlist", "board"],
    queryFn: getBoard,
    refetchInterval: 60_000,
  });

  const items = data?.items ?? [];
  const alerts = data?.alerts ?? [];

  const symbols = items.map((i) => i.symbol);
  const { data: patterns } = useQuery({
    queryKey: ["watchlist", "patterns", symbols],
    queryFn: () => matchPatterns(symbols),
    enabled: symbols.length > 0,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const cols: ColumnsType<BoardItem> = [
    { title: "代码", dataIndex: "symbol", width: 90, render: (v: string) => <span className="num">{v}</span> },
    { title: "名称", dataIndex: "name", width: 100, render: (v: string | null) => v ?? "-" },
    {
      title: "现价",
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
      title: "成交额(亿)",
      dataIndex: "amount",
      align: "right",
      render: (v: number | null) => (v != null ? <span className="num">{(v / 1e8).toFixed(2)}</span> : "-"),
    },
    {
      title: "短线形态",
      key: "patterns",
      width: 200,
      render: (_: unknown, row: BoardItem) => {
        const ps = patterns?.[row.symbol] ?? [];
        return ps.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {ps.map((p) => (
              <Tag key={p} color={PATTERN_COLOR[p] ?? "default"} className="!m-0">
                {p}
              </Tag>
            ))}
          </span>
        ) : (
          <span className="text-slate-300">-</span>
        );
      },
    },
    {
      title: "备注",
      dataIndex: "notes",
      render: (v: string) => <span className="text-xs text-slate-400">{v}</span>,
    },
  ];

  return (
    <PageScaffold>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        <Card
          size="small"
          title="自选股盯盘（快照 5min / 自动刷新 60s）"
          className="lg:col-span-2 flex flex-col"
          classNames={{ body: "flex-1 flex flex-col min-h-0" }}
          extra={data && !data.quote_ready ? <Badge status="warning" text="报价快照刷新中" /> : null}
        >
          {items.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <Empty description="还没有自选股，去选股器或 K 线页加自选" />
            </div>
          ) : (
            <Table<BoardItem>
              rowKey="symbol"
              size="small"
              dataSource={items}
              columns={cols}
              loading={isLoading}
              pagination={false}
              className="flex-1"
            />
          )}
        </Card>

        <Card
          size="small"
          title={`AI 盯盘告警（${alerts.length}）`}
          className="flex flex-col"
          classNames={{ body: "flex-1 flex flex-col min-h-0 overflow-auto" }}
        >
          {alerts.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <Empty description="暂无告警" />
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {alerts.map((a) => (
                <div key={a.id} className="border border-slate-100 rounded px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="num text-sm font-medium">{a.symbol}</span>
                    <Tag color={LEVEL_COLOR[a.level]}>{a.level}</Tag>
                  </div>
                  <div className="text-sm mt-1">{a.signal}</div>
                  <div className="text-xs text-slate-400 mt-1">
                    {a.created_at.slice(0, 19).replace("T", " ")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </PageScaffold>
  );
}
