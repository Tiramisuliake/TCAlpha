import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { PageScaffold } from "@/components/PageScaffold";
import { PermButton } from "@/components/PermButton";
import {
  createRule,
  deleteRule,
  getMeta,
  listLogs,
  listRules,
  testPush,
  updateRule,
  type NotifyLog,
  type NotifyRule,
  type NotifyRuleInput,
} from "@/api/notify";

const { TextArea } = Input;

export default function NotifyPage() {
  const qc = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<NotifyRule | null>(null);
  const [form] = Form.useForm<NotifyRuleInput>();

  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ["notify", "rules"],
    queryFn: listRules,
    staleTime: 30_000,
  });
  const { data: meta } = useQuery({
    queryKey: ["notify", "meta"],
    queryFn: getMeta,
    staleTime: 5 * 60_000,
  });
  const { data: logs = [], isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ["notify", "logs"],
    queryFn: () => listLogs(200),
    staleTime: 5_000,
  });

  const eventTypeOptions = useMemo(() => {
    const opts =
      meta?.event_types.map((e) => ({ label: `${e.type} — ${e.desc}`, value: e.type })) ??
      [];
    // 加上类别通配
    const categories = ["strategy.*", "sim.*", "backtest.*", "ai.alert.*", "quote.*"];
    return [
      ...categories.map((c) => ({ label: `${c}（全部）`, value: c })),
      ...opts,
    ];
  }, [meta]);

  const channelOptions = useMemo(
    () => (meta?.channels ?? ["feishu"]).map((c) => ({ label: c, value: c })),
    [meta],
  );

  const createMut = useMutation({
    mutationFn: createRule,
    onSuccess: () => {
      message.success("规则已创建");
      qc.invalidateQueries({ queryKey: ["notify", "rules"] });
      closeDrawer();
    },
  });
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: NotifyRuleInput }) =>
      updateRule(id, body),
    onSuccess: () => {
      message.success("规则已更新");
      qc.invalidateQueries({ queryKey: ["notify", "rules"] });
      closeDrawer();
    },
  });
  const deleteMut = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["notify", "rules"] });
    },
  });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      name: "",
      match_types: ["strategy.*"],
      channels: ["feishu"],
      feishu_webhook: "",
      feishu_secret: "",
      quiet_hours: "",
      enabled: true,
    });
    setDrawerOpen(true);
  };

  const openEdit = (rule: NotifyRule) => {
    setEditing(rule);
    form.setFieldsValue({
      name: rule.name,
      match_types: rule.match_types,
      channels: rule.channels,
      feishu_webhook: rule.feishu_webhook,
      feishu_secret: rule.feishu_secret,
      quiet_hours: rule.quiet_hours,
      enabled: rule.enabled,
    });
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditing(null);
  };

  const submit = async () => {
    const values = await form.validateFields();
    const body: NotifyRuleInput = {
      ...values,
      match_filters: {},
      feishu_webhook: values.feishu_webhook ?? "",
      feishu_secret: values.feishu_secret ?? "",
      quiet_hours: values.quiet_hours ?? "",
      enabled: values.enabled ?? true,
    };
    if (editing) updateMut.mutate({ id: editing.id, body });
    else createMut.mutate(body);
  };

  const ruleCols: ColumnsType<NotifyRule> = [
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "事件类型",
      dataIndex: "match_types",
      key: "match_types",
      render: (types: string[]) => (
        <Space size={[4, 4]} wrap>
          {types.map((t) => (
            <Tag key={t} color="geekblue">
              {t}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "渠道",
      dataIndex: "channels",
      key: "channels",
      width: 120,
      render: (cs: string[]) => cs.map((c) => <Tag key={c}>{c}</Tag>),
    },
    { title: "静音时段", dataIndex: "quiet_hours", key: "quiet_hours", width: 110 },
    {
      title: "启用",
      dataIndex: "enabled",
      key: "enabled",
      width: 80,
      render: (e: boolean) => (e ? <Tag color="green">on</Tag> : <Tag>off</Tag>),
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_, row) => (
        <Space>
          <PermButton perm="notify.rule.write" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            编辑
          </PermButton>
          <PermButton perm="notify.rule.write" size="small" icon={<SendOutlined />} onClick={() => onTest(row)}>
            测试
          </PermButton>
          <Popconfirm
            title="确认删除？"
            okText="删除"
            cancelText="取消"
            okType="danger"
            onConfirm={() => deleteMut.mutate(row.id)}
          >
            <PermButton perm="notify.rule.write" hideOnDenied size="small" danger icon={<DeleteOutlined />}>
              删
            </PermButton>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const onTest = async (rule: NotifyRule) => {
    const hide = message.loading("发送中…", 0);
    try {
      const res = await testPush({
        rule_id: rule.id,
        content: `[测试] 来自 TCAlpha 通知中心 · 规则「${rule.name}」`,
      });
      hide();
      if (res.success) message.success("发送成功，请到飞书查看");
      else message.error(`发送失败：${res.error ?? "未知错误"}`);
    } catch {
      hide();
    }
  };

  const onTestAdHoc = () => {
    let webhook = "";
    let secret = "";
    let content = "TCAlpha 测试推送";
    Modal.confirm({
      title: "临时测试推送",
      content: (
        <Space direction="vertical" className="!w-full">
          <Input
            placeholder="飞书 webhook"
            onChange={(e) => (webhook = e.target.value)}
          />
          <Input
            placeholder="签名密钥（可空）"
            onChange={(e) => (secret = e.target.value)}
          />
          <Input
            placeholder="消息内容"
            defaultValue={content}
            onChange={(e) => (content = e.target.value)}
          />
        </Space>
      ),
      okText: "发送",
      cancelText: "取消",
      onOk: async () => {
        const res = await testPush({
          feishu_webhook: webhook,
          feishu_secret: secret,
          content,
        });
        if (res.success) message.success("发送成功");
        else message.error(`失败：${res.error ?? "未知错误"}`);
      },
    });
  };

  const logCols: ColumnsType<NotifyLog> = [
    {
      title: "时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (s: string) => s.replace("T", " ").split(".")[0],
    },
    { title: "事件", dataIndex: "event_type", key: "event_type", width: 180 },
    { title: "渠道", dataIndex: "channel", key: "channel", width: 80 },
    {
      title: "结果",
      dataIndex: "success",
      key: "success",
      width: 80,
      render: (s: boolean) =>
        s ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>,
    },
    {
      title: "错误 / 内容",
      key: "detail",
      render: (_, row) =>
        row.error_msg ? (
          <Tooltip title={row.error_msg}>
            <span className="text-red-500 text-xs">{row.error_msg.slice(0, 80)}</span>
          </Tooltip>
        ) : (
          <code className="text-xs text-slate-600">{JSON.stringify(row.payload)}</code>
        ),
    },
  ];

  return (
    <PageScaffold>
      <Card
        title={
          <Space>
            <BellOutlined />
            <span>通知中心</span>
            <Tag color="blue">飞书</Tag>
          </Space>
        }
        extra={
          <Space>
            <PermButton perm="notify.rule.write" icon={<SendOutlined />} onClick={onTestAdHoc}>
              临时测试
            </PermButton>
            <PermButton perm="notify.rule.write" type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建规则
            </PermButton>
          </Space>
        }
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0" }}
      >
        <Tabs
          defaultActiveKey="rules"
          items={[
            {
              key: "rules",
              label: "规则",
              children: (
                <Table<NotifyRule>
                  rowKey="id"
                  size="middle"
                  dataSource={rules}
                  columns={ruleCols}
                  loading={rulesLoading}
                  pagination={{ pageSize: 20 }}
                />
              ),
            },
            {
              key: "logs",
              label: (
                <Space>
                  历史
                  <Tooltip title="刷新">
                    <Button
                      size="small"
                      type="text"
                      icon={<ReloadOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        refetchLogs();
                      }}
                    />
                  </Tooltip>
                </Space>
              ),
              children: (
                <Table<NotifyLog>
                  rowKey="id"
                  size="middle"
                  dataSource={logs}
                  columns={logCols}
                  loading={logsLoading}
                  pagination={{ pageSize: 20 }}
                />
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title={editing ? `编辑规则 #${editing.id}` : "新建规则"}
        open={drawerOpen}
        onClose={closeDrawer}
        width={520}
        extra={
          <Space>
            <Button onClick={closeDrawer}>取消</Button>
            <PermButton
              perm="notify.rule.write"
              type="primary"
              loading={createMut.isPending || updateMut.isPending}
              onClick={submit}
            >
              保存
            </PermButton>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="名称"
            name="name"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如：策略 crash 告警" />
          </Form.Item>
          <Form.Item
            label="事件类型（支持通配符）"
            name="match_types"
            rules={[{ required: true, message: "至少选择一个事件类型" }]}
          >
            <Select
              mode="multiple"
              allowClear
              options={eventTypeOptions}
              placeholder="如 strategy.* 或 ai.alert.warn"
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item
            label="推送渠道"
            name="channels"
            rules={[{ required: true, message: "至少选择一个渠道" }]}
          >
            <Select mode="multiple" options={channelOptions} />
          </Form.Item>
          <Form.Item
            label="飞书 webhook URL"
            name="feishu_webhook"
            tooltip="完整 URL，从飞书机器人设置复制"
          >
            <TextArea autoSize={{ minRows: 2, maxRows: 3 }} placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx" />
          </Form.Item>
          <Form.Item
            label="飞书签名密钥（可空）"
            name="feishu_secret"
            tooltip="仅当机器人开启签名校验时填写"
          >
            <Input.Password placeholder="留空则不签名" />
          </Form.Item>
          <Form.Item
            label="静音时段"
            name="quiet_hours"
            tooltip="格式 HH:MM-HH:MM；跨天用 22:00-08:00；留空 = 不静音"
          >
            <Input placeholder="22:00-08:00" />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Drawer>
    </PageScaffold>
  );
}
