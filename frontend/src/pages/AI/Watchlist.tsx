import { useState } from "react";
import {
  Button,
  Empty,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  addWatch,
  deleteWatch,
  listWatchlist,
  type WatchlistItem,
} from "@/api/watchlist";
import { triggerWatch } from "@/api/ai_alerts";

export default function Watchlist({
  onJumpAlerts,
}: {
  onJumpAlerts?: () => void;
}) {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("");
  const [notes, setNotes] = useState("");

  const { data = [], isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: listWatchlist,
    staleTime: 30_000,
  });

  const addMut = useMutation({
    mutationFn: ({ s, n }: { s: string; n: string }) => addWatch(s, n),
    onSuccess: () => {
      message.success("已加入关注");
      setSymbol("");
      setNotes("");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const delMut = useMutation({
    mutationFn: deleteWatch,
    onSuccess: () => {
      message.success("已移除");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const watchMut = useMutation({
    mutationFn: triggerWatch,
    onSuccess: () => {
      message.success("已派发盯盘任务，1-3 秒后可在「盯盘」tab 查看");
    },
  });

  const cols: ColumnsType<WatchlistItem> = [
    {
      title: "股票",
      dataIndex: "symbol",
      key: "symbol",
      render: (s: string) => <Tag color="blue">{s}</Tag>,
    },
    { title: "备注", dataIndex: "notes", key: "notes" },
    {
      title: "加入时间",
      dataIndex: "added_at",
      key: "added_at",
      width: 170,
      render: (s: string) => s.replace("T", " ").split(".")[0],
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_, row) => (
        <Space>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            loading={watchMut.isPending && watchMut.variables === row.symbol}
            onClick={() => watchMut.mutate(row.symbol)}
          >
            盯一次
          </Button>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => onJumpAlerts?.()}
          >
            查告警
          </Button>
          <Popconfirm
            title="移除关注？"
            okText="移除"
            cancelText="取消"
            okType="danger"
            onConfirm={() => delMut.mutate(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const submit = () => {
    if (!symbol.trim()) {
      message.warning("请输入股票代码");
      return;
    }
    addMut.mutate({ s: symbol.trim(), n: notes.trim() });
  };

  return (
    <div className="flex flex-col gap-3 min-h-0 flex-1">
      <Space.Compact className="!w-full max-w-2xl">
        <Input
          placeholder="股票代码，如 sh600000 / 000001 / 600000.SH"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onPressEnter={submit}
        />
        <Input
          placeholder="备注（可选）"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onPressEnter={submit}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          loading={addMut.isPending}
          onClick={submit}
        >
          加入关注
        </Button>
      </Space.Compact>

      <Table<WatchlistItem>
        size="middle"
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={cols}
        locale={{ emptyText: <Empty description="尚未关注任何股票" /> }}
        pagination={{ pageSize: 20 }}
      />
    </div>
  );
}
