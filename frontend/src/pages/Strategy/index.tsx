import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  message,
} from "antd";
import {
  CaretRightOutlined,
  PauseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import {
  createStrategy,
  deleteStrategy,
  getStrategies,
  getStrategyClasses,
  updateStrategy,
} from "@/api/strategy";
import {
  getStrategyRunning,
  listOrders,
  startStrategy,
  stopStrategy,
} from "@/api/sim";
import { getSymbols } from "@/api/market";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { SimOrder, StrategyClassInfo, StrategyConfig, StrategyCreate, StrategySignal } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  stopped: "default",
  running: "green",
  error: "red",
};

const ORDER_STATUS_COLOR: Record<string, string> = {
  submitted: "processing",
  filled: "success",
  partial: "warning",
  cancelled: "default",
  rejected: "error",
};

export default function StrategyPage() {
  const qc = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editItem, setEditItem] = useState<StrategyConfig | null>(null);
  const [activeStrategyId, setActiveStrategyId] = useState<number | null>(null);
  const [signal, setSignal] = useState<StrategySignal | null>(null);
  const [liveOrders, setLiveOrders] = useState<SimOrder[]>([]);
  const [form] = Form.useForm<StrategyCreate & { paramsFast?: number; paramsSlow?: number }>();

  // 订单 WS（用户级别，不随策略切换断开）
  const onOrderMsg = useCallback((raw: string) => {
    try {
      const o = JSON.parse(raw) as SimOrder;
      setLiveOrders((prev) => {
        const idx = prev.findIndex((x) => x.id === o.id);
        if (idx >= 0) {
          const copy = [...prev];
          copy[idx] = o;
          return copy;
        }
        return [o, ...prev].slice(0, 50);
      });
      qc.invalidateQueries({ queryKey: ["sim", "orders"] });
    } catch {
      /* ignore */
    }
  }, [qc]);

  useWebSocket("ws://localhost:8000/ws/orders?user_id=1", onOrderMsg);

  // 信号 WS（随选中策略变化）
  const onSignalMsg = useCallback((raw: string) => {
    try {
      setSignal(JSON.parse(raw) as StrategySignal);
    } catch {
      /* ignore */
    }
  }, []);

  useWebSocket(
    activeStrategyId ? `ws://localhost:8000/ws/signals?strategy_id=${activeStrategyId}` : "",
    onSignalMsg,
    { enabled: !!activeStrategyId }
  );

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ["strategy", "list"],
    queryFn: getStrategies,
    refetchInterval: 5000,
  });

  const { data: classes = [] } = useQuery({
    queryKey: ["strategy", "classes"],
    queryFn: getStrategyClasses,
  });

  const { data: symbolsResp } = useQuery({
    queryKey: ["symbols", { limit: 200 }],
    queryFn: () => getSymbols({ limit: 200 }),
  });

  const { data: runningData } = useQuery({
    queryKey: ["strategy", activeStrategyId, "running"],
    queryFn: () => getStrategyRunning(activeStrategyId!),
    enabled: !!activeStrategyId,
    refetchInterval: 3000,
  });

  const { data: ordersData = [] } = useQuery({
    queryKey: ["sim", "orders", activeStrategyId],
    queryFn: () => listOrders(activeStrategyId ?? undefined),
    enabled: !!activeStrategyId,
  });

  const symbolOptions = (symbolsResp?.items ?? []).map((s) => ({
    value: s.symbol,
    label: `${s.code} ${s.name}`,
  }));

  const classOptions = classes.map((c: StrategyClassInfo) => ({
    value: c.class_name,
    label: c.class_name,
  }));

  const createMut = useMutation({
    mutationFn: createStrategy,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategy", "list"] });
      message.success("策略已创建");
      setDrawerOpen(false);
      form.resetFields();
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: StrategyCreate }) =>
      updateStrategy(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategy", "list"] });
      message.success("策略已更新");
      setDrawerOpen(false);
      setEditItem(null);
      form.resetFields();
    },
  });

  const deleteMut = useMutation({
    mutationFn: deleteStrategy,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategy", "list"] });
      message.success("策略已删除");
    },
  });

  const startMut = useMutation({
    mutationFn: startStrategy,
    onSuccess: (_, id) => {
      message.success("策略已启动");
      qc.invalidateQueries({ queryKey: ["strategy", "list"] });
      qc.invalidateQueries({ queryKey: ["strategy", id, "running"] });
      setActiveStrategyId(id);
    },
  });

  const stopMut = useMutation({
    mutationFn: stopStrategy,
    onSuccess: () => {
      message.info("停止信号已发送");
      qc.invalidateQueries({ queryKey: ["strategy", "list"] });
    },
  });

  function openCreate() {
    setEditItem(null);
    form.resetFields();
    setDrawerOpen(true);
  }

  function openEdit(item: StrategyConfig) {
    setEditItem(item);
    const params = item.params as Record<string, number>;
    form.setFieldsValue({
      name: item.name,
      class_name: item.class_name,
      symbol: item.symbol,
      paramsFast: params.fast ?? 10,
      paramsSlow: params.slow ?? 20,
    });
    setDrawerOpen(true);
  }

  function onFinish(values: StrategyCreate & { paramsFast?: number; paramsSlow?: number }) {
    const { paramsFast, paramsSlow, ...rest } = values;
    const payload: StrategyCreate = {
      ...rest,
      params: { fast: paramsFast ?? 10, slow: paramsSlow ?? 20 },
    };
    if (editItem) {
      updateMut.mutate({ id: editItem.id, payload });
    } else {
      createMut.mutate(payload);
    }
  }

  function confirmDelete(id: number) {
    Modal.confirm({
      title: "确认删除策略？",
      content: "删除后不可恢复",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => deleteMut.mutate(id),
    });
  }

  const isRunning = runningData?.running ?? false;
  const displayOrders = liveOrders.length > 0 ? liveOrders : ordersData;

  const strategyColumns: ColumnsType<StrategyConfig> = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "策略类", dataIndex: "class_name", key: "class_name", width: 150 },
    { title: "标的", dataIndex: "symbol", key: "symbol", width: 100 },
    {
      title: "参数",
      key: "params",
      render: (_, r) => (
        <span className="text-xs text-slate-500">{JSON.stringify(r.params)}</span>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (s: string) => <Tag color={STATUS_COLOR[s] ?? "default"}>{s}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 200,
      render: (_, r) => (
        <Space size="small">
          <Button
            size="small"
            type={activeStrategyId === r.id ? "primary" : "default"}
            onClick={() => {
              setActiveStrategyId(r.id);
              setSignal(null);
              setLiveOrders([]);
            }}
          >
            选中
          </Button>
          <Button size="small" onClick={() => openEdit(r)}>编辑</Button>
          <Button size="small" danger onClick={() => confirmDelete(r.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  const orderColumns: ColumnsType<SimOrder> = [
    { title: "时间", dataIndex: "created_at", width: 90, render: (v) => v.slice(11, 19) },
    {
      title: "方向",
      key: "dir",
      width: 70,
      render: (_, r) => (
        <Tag color={r.direction === "long" && r.offset === "open" ? "red" : r.direction === "long" && r.offset === "close" ? "orange" : "green"}>
          {r.offset === "open" ? (r.direction === "long" ? "买入" : "卖空") : (r.direction === "long" ? "卖出" : "平空")}
        </Tag>
      ),
    },
    { title: "价格", dataIndex: "price", render: (v) => (+v).toFixed(2) },
    { title: "量", dataIndex: "volume", width: 60 },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (s: string) => <Badge status={ORDER_STATUS_COLOR[s] as "processing" | "success" | "warning" | "default" | "error"} text={s} />,
    },
  ];

  const isSubmitting = createMut.isPending || updateMut.isPending;

  return (
    <div className="space-y-4">
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card
            title="策略列表"
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新建
              </Button>
            }
          >
            <Table<StrategyConfig>
              dataSource={strategies}
              columns={strategyColumns}
              rowKey="id"
              loading={isLoading}
              pagination={{ pageSize: 8 }}
              rowClassName={(r) => r.id === activeStrategyId ? "!bg-blue-50" : ""}
              size="small"
            />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          {activeStrategyId ? (
            <div className="space-y-4">
              {/* 启停控制 */}
              <Card
                title={`策略控制 #${activeStrategyId}`}
                size="small"
                extra={
                  isRunning ? (
                    <Button
                      danger
                      icon={<PauseOutlined />}
                      loading={stopMut.isPending}
                      onClick={() => stopMut.mutate(activeStrategyId)}
                    >
                      停止
                    </Button>
                  ) : (
                    <Button
                      type="primary"
                      icon={<CaretRightOutlined />}
                      loading={startMut.isPending}
                      onClick={() => startMut.mutate(activeStrategyId)}
                    >
                      启动
                    </Button>
                  )
                }
              >
                <div className="flex items-center gap-2">
                  <Badge status={isRunning ? "processing" : "default"} />
                  <span className={isRunning ? "text-green-600 font-medium" : "text-slate-400"}>
                    {isRunning ? "运行中" : "已停止"}
                  </span>
                </div>
              </Card>

              {/* 信号面板 */}
              {signal && (
                <Card title="最新信号" size="small">
                  <Row gutter={8}>
                    <Col span={8}>
                      <Statistic
                        title="方向"
                        value={signal.direction > 0 ? "多头" : signal.direction < 0 ? "空头" : "中性"}
                        valueStyle={{ color: signal.direction > 0 ? "#ef4444" : signal.direction < 0 ? "#10b981" : "#94a3b8" }}
                      />
                    </Col>
                    <Col span={8}>
                      <Statistic title="强度" value={signal.strength} suffix="%" />
                    </Col>
                    <Col span={8}>
                      <Statistic title="持仓" value={signal.pos} />
                    </Col>
                  </Row>
                  <div className="mt-2 text-sm text-slate-600 bg-slate-50 rounded px-3 py-2">
                    {signal.tip || "无信号"}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">Bar: {signal.bar_dt}</div>
                </Card>
              )}

              {/* 订单列表 */}
              <Card
                title={
                  <span>
                    模拟订单
                    {isRunning && (
                      <Badge className="ml-2" status="processing" text="实时" />
                    )}
                  </span>
                }
                size="small"
              >
                <Table<SimOrder>
                  dataSource={displayOrders}
                  columns={orderColumns}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 6 }}
                />
              </Card>
            </div>
          ) : (
            <Card>
              <div className="text-slate-400 py-12 text-center">
                <p className="text-base mb-1">选中一个策略</p>
                <p className="text-sm">可启停运行、查看实时信号和订单</p>
              </div>
            </Card>
          )}
        </Col>
      </Row>

      <Drawer
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setEditItem(null); form.resetFields(); }}
        title={editItem ? "编辑策略" : "新建策略"}
        width={480}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={isSubmitting} onClick={() => form.submit()}>保存</Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item label="策略名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="如：MA10/20 平安银行" />
          </Form.Item>
          <Form.Item label="策略类" name="class_name" rules={[{ required: true }]}>
            <Select options={classOptions} placeholder="选择策略类型" />
          </Form.Item>
          <Form.Item label="标的股票" name="symbol" rules={[{ required: true }]}>
            <Select
              showSearch
              options={symbolOptions}
              filterOption={(input, opt) =>
                (opt?.label ?? "").toLowerCase().includes(input.toLowerCase())
              }
              placeholder="搜索股票代码或名称"
            />
          </Form.Item>
          <Form.Item label="快线周期" name="paramsFast" initialValue={10}>
            <InputNumber min={2} max={200} className="!w-full" />
          </Form.Item>
          <Form.Item label="慢线周期" name="paramsSlow" initialValue={20}>
            <InputNumber min={2} max={500} className="!w-full" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
