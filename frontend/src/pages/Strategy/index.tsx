import { useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import {
  createStrategy,
  deleteStrategy,
  getStrategies,
  getStrategyClasses,
  updateStrategy,
} from "@/api/strategy";
import { getSymbols } from "@/api/market";
import type { StrategyClassInfo, StrategyConfig, StrategyCreate } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  stopped: "default",
  running: "green",
  error: "red",
};

export default function Strategy() {
  const qc = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editItem, setEditItem] = useState<StrategyConfig | null>(null);
  const [form] = Form.useForm<StrategyCreate & { paramsFast?: number; paramsSlow?: number }>();

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ["strategy", "list"],
    queryFn: getStrategies,
  });

  const { data: classes = [] } = useQuery({
    queryKey: ["strategy", "classes"],
    queryFn: getStrategyClasses,
  });

  const { data: symbolsResp } = useQuery({
    queryKey: ["symbols", { limit: 200 }],
    queryFn: () => getSymbols({ limit: 200 }),
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

  const columns: ColumnsType<StrategyConfig> = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "策略类", dataIndex: "class_name", key: "class_name", width: 160 },
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
      key: "status",
      width: 80,
      render: (s: string) => <Tag color={STATUS_COLOR[s] ?? "default"}>{s}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 120,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Button size="small" danger onClick={() => confirmDelete(r.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const isSubmitting = createMut.isPending || updateMut.isPending;

  return (
    <div className="p-2">
      <Card
        title="策略管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建策略
          </Button>
        }
      >
        <Table<StrategyConfig>
          dataSource={strategies}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Drawer
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditItem(null);
          form.resetFields();
        }}
        title={editItem ? "编辑策略" : "新建策略"}
        width={480}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={isSubmitting} onClick={() => form.submit()}>
              保存
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item label="策略名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="如：MA10/20 平安银行" />
          </Form.Item>
          <Form.Item
            label="策略类"
            name="class_name"
            rules={[{ required: true, message: "请选择策略类" }]}
          >
            <Select options={classOptions} placeholder="选择策略类型" />
          </Form.Item>
          <Form.Item
            label="标的股票"
            name="symbol"
            rules={[{ required: true, message: "请选择股票" }]}
          >
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
