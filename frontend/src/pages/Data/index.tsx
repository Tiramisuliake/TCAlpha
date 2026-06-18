import { useState } from "react";
import { Card, Col, Input, Progress, Row, Select, Space, Statistic, Table, Tag, message } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import { getDataHealth, getSymbols, refreshSymbols, triggerDownload } from "@/api/market";
import type { Symbol, SyncFailure } from "@/types";
import { PageScaffold } from "@/components/PageScaffold";
import { PermButton } from "@/components/PermButton";

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

  const { data: health } = useQuery({
    queryKey: ["data", "health"],
    queryFn: getDataHealth,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const refreshMut = useMutation({
    mutationFn: refreshSymbols,
    onSuccess: (res) => {
      message.success(`刷新任务已提交（task: ${res.task_id.slice(0, 8)}…）`);
    },
  });

  const failureCols: ColumnsType<SyncFailure> = [
    { title: "代码", dataIndex: "symbol", width: 100, render: (v) => <span className="font-mono">{v}</span> },
    { title: "周期", dataIndex: "period", width: 70 },
    { title: "错误", dataIndex: "error", render: (v) => <span className="text-xs text-red-500">{v}</span> },
    {
      title: "时间", dataIndex: "updated_at", width: 160,
      render: (v: string | null) => (v ? <span className="num text-xs">{v.slice(0, 19).replace("T", " ")}</span> : "—"),
    },
  ];

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
        <PermButton
          perm="data.download"
          size="small"
          icon={<DownloadOutlined />}
          loading={downloadMut.isPending}
          onClick={() => downloadMut.mutate(row.symbol)}
        >
          下载K线
        </PermButton>
      ),
    },
  ];

  return (
    <PageScaffold>
      <Card size="small" title="数据健康（K 线覆盖度 + 同步状态）" className="mb-3">
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} lg={8}>
            <div className="flex items-center gap-4">
              <Progress
                type="dashboard"
                size={88}
                percent={Math.round((health?.coverage_rate ?? 0) * 100)}
                strokeColor={(health?.coverage_rate ?? 0) >= 0.8 ? "#10b981" : "#f59e0b"}
              />
              <div>
                <div className="text-xs text-slate-400">K 线覆盖</div>
                <div className="num text-lg font-medium">
                  {health?.bar1d_covered ?? 0} / {health?.symbols_total ?? 0}
                </div>
                <div className="text-xs text-slate-400">已下载 / 活跃标的</div>
              </div>
            </div>
          </Col>
          <Col xs={12} lg={4}>
            <Statistic title="同步成功" value={health?.sync_ok ?? 0} valueStyle={{ fontSize: 20, color: "#10b981" }} />
          </Col>
          <Col xs={12} lg={4}>
            <Statistic title="同步失败" value={health?.sync_failed ?? 0} valueStyle={{ fontSize: 20, color: (health?.sync_failed ?? 0) > 0 ? "#ef4444" : undefined }} />
          </Col>
          <Col xs={24} lg={8}>
            {(health?.recent_failures?.length ?? 0) > 0 ? (
              <Table<SyncFailure>
                rowKey={(r) => `${r.symbol}-${r.period}`}
                size="small"
                dataSource={health?.recent_failures}
                columns={failureCols}
                pagination={false}
                scroll={{ y: 120 }}
              />
            ) : (
              <div className="text-xs text-slate-400">近期无同步失败 ✓</div>
            )}
          </Col>
        </Row>
      </Card>

      <Card
        title="股票列表"
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
        extra={
          <PermButton
            perm="data.download"
            type="primary"
            icon={<ReloadOutlined />}
            loading={refreshMut.isPending}
            onClick={() => refreshMut.mutate()}
          >
            刷新股票列表
          </PermButton>
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
          className="flex-1"
        />
      </Card>
    </PageScaffold>
  );
}
