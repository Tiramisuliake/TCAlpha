import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelOrder,
  listOrders,
  listPositions,
  placeOrder,
} from "@/api/sim";
import { getSymbols } from "@/api/market";
import type {
  PlaceOrderRequest,
  PositionSummary,
  SimOrder,
} from "@/types";
import { PageScaffold } from "@/components/PageScaffold";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAuthStore, wsUrl as buildWsUrl } from "@/store/useAuthStore";

const STATUS_COLOR: Record<SimOrder["status"], string> = {
  submitted: "processing",
  partial: "gold",
  filled: "success",
  cancelled: "default",
  rejected: "error",
};

const STATUS_LABEL: Record<SimOrder["status"], string> = {
  submitted: "已提交",
  partial: "部分成交",
  filled: "已成交",
  cancelled: "已撤单",
  rejected: "已拒单",
};

function OrderForm({
  symbolOptions,
  symbolSearch,
  onSearch,
  onSubmit,
  submitting,
}: {
  symbolOptions: { value: string; label: string }[];
  symbolSearch: string;
  onSearch: (s: string) => void;
  onSubmit: (payload: PlaceOrderRequest) => void;
  submitting: boolean;
}) {
  const [form] = Form.useForm<PlaceOrderRequest>();

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{ direction: "long", offset: "open", volume: 100 }}
      onFinish={onSubmit}
    >
      <Form.Item
        label="股票"
        name="symbol"
        rules={[{ required: true, message: "请选择股票" }]}
      >
        <Select
          showSearch
          placeholder="输入代码或名称"
          options={symbolOptions}
          filterOption={false}
          onSearch={onSearch}
          notFoundContent={symbolSearch ? "未找到" : "请输入代码或名称"}
        />
      </Form.Item>

      <Form.Item label="方向" name="direction" rules={[{ required: true }]}>
        <Segmented
          block
          options={[
            { label: "买入（多）", value: "long" },
            { label: "卖出（空）", value: "short" },
          ]}
        />
      </Form.Item>

      <Form.Item label="开 / 平" name="offset" rules={[{ required: true }]}>
        <Segmented
          block
          options={[
            { label: "开仓", value: "open" },
            { label: "平仓", value: "close" },
          ]}
        />
      </Form.Item>

      <Form.Item
        label="数量（向下取整到 100 股）"
        name="volume"
        rules={[
          { required: true, type: "number", min: 100, message: "至少 100 股" },
        ]}
      >
        <InputNumber min={100} step={100} className="!w-full" />
      </Form.Item>

      <Button
        type="primary"
        htmlType="submit"
        loading={submitting}
        block
        size="large"
      >
        市价单提交
      </Button>
      <div className="text-xs text-slate-400 mt-2">
        ⚠️ 模拟交易：按当前实时报价立即成交，无资金校验。
      </div>
    </Form>
  );
}

export default function TradePage() {
  const qc = useQueryClient();
  const userId = useAuthStore((s) => s.userId);
  const [symbolSearch, setSymbolSearch] = useState("");

  const { data: symbolsData } = useQuery({
    queryKey: ["symbols", { search: symbolSearch, limit: 50 }],
    queryFn: () => getSymbols({ search: symbolSearch || undefined, limit: 50 }),
    staleTime: 60_000,
  });

  const symbolOptions = useMemo(
    () =>
      symbolsData?.items.map((s) => ({
        value: s.symbol,
        label: `${s.code} ${s.name}`,
      })) ?? [],
    [symbolsData]
  );

  const ordersQuery = useQuery({
    queryKey: ["sim", "orders"],
    queryFn: () => listOrders(undefined, 50),
    staleTime: 10_000,
  });

  const positionsQuery = useQuery({
    queryKey: ["sim", "positions"],
    queryFn: listPositions,
    staleTime: 10_000,
  });

  const placeMut = useMutation({
    mutationFn: placeOrder,
    onSuccess: (order) => {
      message.success(
        order.status === "filled"
          ? `已成交 ${order.symbol} ${order.filled_volume} 股 @ ${order.price.toFixed(2)}`
          : `订单已提交，状态：${STATUS_LABEL[order.status]}`
      );
      qc.invalidateQueries({ queryKey: ["sim", "orders"] });
      qc.invalidateQueries({ queryKey: ["sim", "positions"] });
    },
  });

  const cancelMut = useMutation({
    mutationFn: cancelOrder,
    onSuccess: (order) => {
      message.success(`订单 #${order.id} 当前状态：${STATUS_LABEL[order.status]}`);
      qc.invalidateQueries({ queryKey: ["sim", "orders"] });
    },
  });

  // 实时刷新：监听 /ws/orders（多 worker 通过 Redis 广播；按当前用户订阅）
  const wsUrl = useMemo(() => {
    if (!userId) return "";
    return buildWsUrl("/ws/orders");
  }, [userId]);

  useWebSocket(
    wsUrl,
    () => {
      qc.invalidateQueries({ queryKey: ["sim", "orders"] });
      qc.invalidateQueries({ queryKey: ["sim", "positions"] });
    },
    { enabled: !!userId }
  );

  // 切换标签页回来时强制刷新
  useEffect(() => {
    const onFocus = () => {
      qc.invalidateQueries({ queryKey: ["sim", "orders"] });
      qc.invalidateQueries({ queryKey: ["sim", "positions"] });
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [qc]);

  const positionCols: ColumnsType<PositionSummary> = [
    { title: "股票", dataIndex: "symbol", key: "symbol" },
    {
      title: "净仓位",
      dataIndex: "net_position",
      key: "net_position",
      align: "right",
      render: (v: number) => (
        <span className={v > 0 ? "text-red-500" : "text-green-500"}>
          {v > 0 ? `+${v}` : v}
        </span>
      ),
    },
  ];

  const orderCols: ColumnsType<SimOrder> = [
    { title: "ID", dataIndex: "id", key: "id", width: 64 },
    { title: "股票", dataIndex: "symbol", key: "symbol", width: 110 },
    {
      title: "方向",
      dataIndex: "direction",
      key: "direction",
      width: 70,
      render: (d: string) =>
        d === "long" ? (
          <Tag color="red">多</Tag>
        ) : (
          <Tag color="green">空</Tag>
        ),
    },
    {
      title: "开平",
      dataIndex: "offset",
      key: "offset",
      width: 70,
      render: (o: string) => (o === "open" ? "开仓" : "平仓"),
    },
    {
      title: "价格",
      dataIndex: "price",
      key: "price",
      align: "right",
      render: (v: number) => v.toFixed(2),
    },
    {
      title: "数量 / 已成",
      key: "vol",
      align: "right",
      render: (_: unknown, row: SimOrder) =>
        `${row.filled_volume} / ${row.volume}`,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: SimOrder["status"]) => (
        <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag>
      ),
    },
    {
      title: "时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (s: string) => new Date(s).toLocaleString(),
    },
    {
      title: "操作",
      key: "actions",
      width: 80,
      render: (_: unknown, row: SimOrder) =>
        row.status === "submitted" ? (
          <Button
            size="small"
            danger
            loading={cancelMut.isPending && cancelMut.variables === row.id}
            onClick={() =>
              Modal.confirm({
                title: `撤单 #${row.id}?`,
                content: `${row.symbol} ${row.direction === "long" ? "多" : "空"} ${row.volume} 股`,
                okText: "撤单",
                okType: "danger",
                cancelText: "取消",
                onOk: () => cancelMut.mutate(row.id),
              })
            }
          >
            撤单
          </Button>
        ) : null,
    },
  ];

  return (
    <PageScaffold>
      <Row gutter={[12, 12]} className="flex-1 min-h-0">
        {/* 左：下单板 */}
        <Col xs={24} lg={7} className="flex">
          <Card title="模拟下单" className="flex-1" classNames={{ body: "flex flex-col" }}>
            <OrderForm
              symbolOptions={symbolOptions}
              symbolSearch={symbolSearch}
              onSearch={setSymbolSearch}
              onSubmit={(payload) => placeMut.mutate(payload)}
              submitting={placeMut.isPending}
            />
          </Card>
        </Col>

        {/* 右：持仓 + 订单 */}
        <Col xs={24} lg={17} className="flex flex-col">
          <Card
            title="当前持仓"
            size="small"
            className="mb-3"
            extra={
              <Button
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                onClick={() =>
                  qc.invalidateQueries({ queryKey: ["sim", "positions"] })
                }
              >
                刷新
              </Button>
            }
          >
            <Table<PositionSummary>
              size="small"
              rowKey="symbol"
              loading={positionsQuery.isLoading}
              dataSource={positionsQuery.data ?? []}
              columns={positionCols}
              pagination={false}
              locale={{ emptyText: "暂无持仓" }}
            />
          </Card>

          <Card
            title="订单流（最近 50 条）"
            size="small"
            className="flex-1"
            classNames={{ body: "flex-1 flex flex-col min-h-0 overflow-auto" }}
            extra={
              <Space>
                <Tag color="processing">实时 WS</Tag>
                <Button
                  size="small"
                  type="text"
                  icon={<ReloadOutlined />}
                  onClick={() =>
                    qc.invalidateQueries({ queryKey: ["sim", "orders"] })
                  }
                >
                  刷新
                </Button>
              </Space>
            }
          >
            <Table<SimOrder>
              size="small"
              rowKey="id"
              loading={ordersQuery.isLoading}
              dataSource={ordersQuery.data ?? []}
              columns={orderCols}
              pagination={false}
              scroll={{ y: "calc(100% - 36px)" }}
            />
          </Card>
        </Col>
      </Row>
    </PageScaffold>
  );
}
