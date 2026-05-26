import { useState } from "react";
import { Button, Card, Input, Select, Space, Table, Tag, message } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import { getSymbols, refreshSymbols, triggerDownload } from "@/api/market";
import type { Symbol } from "@/types";

const EXCHANGES = [
  { value: "", label: "全部" },
  { value: "SH", label: "上交所" },
  { value: "SZ", label: "深交所" },
  { value: "BJ", label: "北交所" },
];

export default function DataMgr() {
  const [search, setSearch] = useState("");
  const [exchange, setExchange] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["symbols", { search, exchange, page, pageSize }],
    queryFn: () =>
      getSymbols({ search: search || undefined, exchange: exchange || undefined, limit: pageSize, offset: (page - 1) * pageSize }),
    staleTime: 60_000,
  });

  const refreshMut = useMutation({
    mutationFn: refreshSymbols,
    onSuccess: (res) => {
      message.success(`刷新任务已提交（task: ${res.task_id.slice(0, 8)}…）`);
    },
  });

  const downloadMut = useMutation({
    mutationFn: (symbol: string) => triggerDownload(symbol),
    onSuccess: (_, symbol) => {
      message.success(`${symbol} 下载任务已提交`);
      qc.invalidateQueries({ queryKey: ["symbols"] });
    },
  });

  const columns: ColumnsType<Symbol> = [
    { title: "代码", dataIndex: "symbol", key: "symbol", width: 100, render: (v) => <span className="font-mono">{v}</span> },
    { title: "名称", dataIndex: "name", key: "name", width: 120 },
    {
      title: "交易所", dataIndex: "exchange", key: "exchange", width: 90,
      render: (v) => <Tag color={v === "SH" ? "blue" : v === "SZ" ? "green" : "orange"}>{v}</Tag>,
    },
    { title: "行业", dataIndex: "industry", key: "industry", width: 120, render: (v) => v ?? "—" },
    { title: "上市日期", dataIndex: "list_date", key: "list_date", width: 110, render: (v) => v ?? "—" },
    {
      title: "状态", dataIndex: "is_active", key: "is_active", width: 80,
      render: (v) => <Tag color={v ? "green" : "default"}>{v ? "正常" : "停牌"}</Tag>,
    },
    {
      title: "操作", key: "actions", width: 90,
      render: (_, row) => (
        <Button
          size="small"
          icon={<DownloadOutlined />}
          loading={downloadMut.isPending}
          onClick={() => downloadMut.mutate(row.symbol)}
        >
          下载K线
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <Card
        title="股票列表"
        extra={
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={refreshMut.isPending}
            onClick={() => refreshMut.mutate()}
          >
            刷新股票列表
          </Button>
        }
      >
        <Space className="mb-4 flex flex-wrap gap-2">
          <Input.Search
            placeholder="搜索代码或名称"
            allowClear
            style={{ width: 220 }}
            onSearch={(v) => { setSearch(v); setPage(1); }}
            onChange={(e) => { if (!e.target.value) { setSearch(""); setPage(1); } }}
          />
          <Select
            value={exchange}
            onChange={(v) => { setExchange(v); setPage(1); }}
            options={EXCHANGES}
            style={{ width: 120 }}
          />
        </Space>

        <Table<Symbol>
          dataSource={data?.items}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
          locale={{ emptyText: "暂无数据，请点击「刷新股票列表」拉取" }}
        />
      </Card>
    </div>
  );
}
