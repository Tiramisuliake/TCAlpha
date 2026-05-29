import { useState } from "react";
import {
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  KeyOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRole,
  deleteRole,
  getRole,
  listPermissions,
  listRoles,
  setRolePermissions,
  updateRole,
} from "@/api/system";
import type {
  DataScope,
  PermissionOut,
  RoleCreate,
  RoleOut,
  RoleUpdate,
} from "@/types";

const { Title, Text } = Typography;

const SCOPE_OPTIONS: { value: DataScope; label: string }[] = [
  { value: "self", label: "self（仅本人数据）" },
  { value: "dept", label: "dept（本部门）" },
  { value: "all", label: "all（所有数据）" },
];

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; role: RoleOut }
  | { kind: "permissions"; role: RoleOut };

export default function SystemRolesPage() {
  const { message } = App.useApp();
  const qc = useQueryClient();

  const { data: roles, isLoading } = useQuery({
    queryKey: ["system", "roles"],
    queryFn: listRoles,
  });

  const { data: permissions } = useQuery({
    queryKey: ["system", "permissions"],
    queryFn: listPermissions,
  });

  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const close = () => setModal({ kind: "closed" });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["system", "roles"] });

  const createMut = useMutation({
    mutationFn: (p: RoleCreate) => createRole(p),
    onSuccess: () => {
      message.success("角色已创建");
      invalidate();
      close();
    },
  });

  const updateMut = useMutation({
    mutationFn: (vars: { id: number; payload: RoleUpdate }) =>
      updateRole(vars.id, vars.payload),
    onSuccess: () => {
      message.success("角色已更新");
      invalidate();
      close();
    },
  });

  const permsMut = useMutation({
    mutationFn: (vars: { id: number; codes: string[] }) =>
      setRolePermissions(vars.id, vars.codes),
    onSuccess: () => {
      message.success("权限已更新");
      qc.invalidateQueries({ queryKey: ["system", "role-detail"] });
      close();
    },
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteRole(id),
    onSuccess: () => {
      message.success("角色已删除");
      invalidate();
    },
  });

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    {
      title: "代码",
      dataIndex: "code",
      width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: "名称", dataIndex: "name", width: 160 },
    {
      title: "数据范围",
      dataIndex: "data_scope",
      width: 140,
      render: (v: DataScope) => {
        const color = v === "all" ? "gold" : v === "dept" ? "geekblue" : "default";
        return <Tag color={color}>{v}</Tag>;
      },
    },
    { title: "描述", dataIndex: "description" },
    {
      title: "操作",
      width: 220,
      fixed: "right" as const,
      render: (_: unknown, r: RoleOut) => (
        <Space size="small">
          <Tooltip title="编辑基本资料">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => setModal({ kind: "edit", role: r })}
            />
          </Tooltip>
          <Tooltip title="配权限">
            <Button
              size="small"
              icon={<KeyOutlined />}
              onClick={() => setModal({ kind: "permissions", role: r })}
            />
          </Tooltip>
          <Popconfirm
            title={`删除角色 ${r.code} ？`}
            description="此操作不可撤销，且会自动解绑所有持有此角色的用户。"
            onConfirm={() => delMut.mutate(r.id)}
            disabled={r.code === "admin"}
          >
            <Tooltip title={r.code === "admin" ? "内置 admin 角色不可删除" : "删除"}>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={r.code === "admin"}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-3 h-full">
      <Card
        size="small"
        title={<Title level={5} className="!mb-0">角色管理</Title>}
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModal({ kind: "create" })}
          >
            新建角色
          </Button>
        }
      >
        <Table<RoleOut>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={roles || []}
          columns={columns}
          pagination={false}
          scroll={{ x: 1000 }}
        />
      </Card>

      <RoleFormModal
        open={modal.kind === "create"}
        loading={createMut.isPending}
        onCancel={close}
        onSubmit={(payload) => createMut.mutate(payload as RoleCreate)}
      />

      <RoleFormModal
        open={modal.kind === "edit"}
        role={modal.kind === "edit" ? modal.role : undefined}
        loading={updateMut.isPending}
        onCancel={close}
        onSubmit={(payload) =>
          modal.kind === "edit" &&
          updateMut.mutate({ id: modal.role.id, payload })
        }
      />

      <PermissionsModal
        open={modal.kind === "permissions"}
        role={modal.kind === "permissions" ? modal.role : null}
        permissions={permissions || []}
        loading={permsMut.isPending}
        onCancel={close}
        onSubmit={(codes) =>
          modal.kind === "permissions" &&
          permsMut.mutate({ id: modal.role.id, codes })
        }
      />
    </div>
  );
}

// ── 角色新建 / 编辑 ──────────────────────────────────────

function RoleFormModal(props: {
  open: boolean;
  role?: RoleOut;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (payload: RoleCreate | RoleUpdate) => void;
}) {
  const [form] = Form.useForm();
  const editing = !!props.role;
  return (
    <Modal
      title={editing ? `编辑角色  ${props.role!.code}` : "新建角色"}
      open={props.open}
      onCancel={props.onCancel}
      onOk={() => form.submit()}
      confirmLoading={props.loading}
      destroyOnHidden
      forceRender
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={
          editing
            ? {
                name: props.role!.name,
                data_scope: props.role!.data_scope,
                description: props.role!.description,
              }
            : { data_scope: "self" as DataScope }
        }
        onFinish={(v) => props.onSubmit(v)}
      >
        {!editing && (
          <Form.Item
            label="代码"
            name="code"
            rules={[{ required: true, max: 64, pattern: /^[a-z0-9._-]+$/, message: "仅小写字母 / 数字 / . _ -" }]}
            tooltip="一旦创建不可更改；建议小写英文，例如 ops / quant"
          >
            <Input />
          </Form.Item>
        )}
        <Form.Item label="名称" name="name" rules={[{ required: true, max: 128 }]}>
          <Input />
        </Form.Item>
        <Form.Item label="数据范围" name="data_scope" rules={[{ required: true }]}>
          <Select options={SCOPE_OPTIONS} />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input.TextArea rows={2} maxLength={256} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ── 权限分配（按 category 分组的 Collapse + Checkbox 树）────

function PermissionsModal(props: {
  open: boolean;
  role: RoleOut | null;
  permissions: PermissionOut[];
  loading: boolean;
  onCancel: () => void;
  onSubmit: (codes: string[]) => void;
}) {
  const [checked, setChecked] = useState<string[]>([]);

  // 拉详情拿当前 permission_codes
  const detailQuery = useQuery({
    queryKey: ["system", "role-detail", props.role?.id],
    queryFn: () => getRole(props.role!.id),
    enabled: !!props.role && props.open,
  });

  // 当 detail 加载完，初始化勾选
  if (
    detailQuery.data &&
    props.open &&
    detailQuery.data.id === props.role?.id &&
    checked.length === 0 &&
    detailQuery.data.permission_codes.length > 0
  ) {
    setChecked(detailQuery.data.permission_codes);
  }

  // 按 category 分组
  const byCategory = props.permissions.reduce<Record<string, PermissionOut[]>>(
    (acc, p) => {
      (acc[p.category] ??= []).push(p);
      return acc;
    },
    {},
  );
  const categories = Object.keys(byCategory).sort();

  const onCategoryToggle = (cat: string, allChecked: boolean) => {
    const catCodes = byCategory[cat].map((p) => p.code);
    setChecked((prev) =>
      allChecked
        ? Array.from(new Set([...prev, ...catCodes]))
        : prev.filter((c) => !catCodes.includes(c)),
    );
  };

  const close = () => {
    setChecked([]);
    props.onCancel();
  };

  return (
    <Modal
      title={`配权限  ${props.role?.code ?? ""}`}
      open={props.open}
      onCancel={close}
      onOk={() => props.onSubmit(checked)}
      confirmLoading={props.loading}
      width={720}
      destroyOnHidden
      forceRender
    >
      <div className="mb-3 flex items-center justify-between">
        <Text type="secondary">共 {props.permissions.length} 个权限点，已选 {checked.length}</Text>
        <Space>
          <Button size="small" onClick={() => setChecked(props.permissions.map((p) => p.code))}>
            全选
          </Button>
          <Button size="small" onClick={() => setChecked([])}>
            清空
          </Button>
        </Space>
      </div>
      <Collapse
        size="small"
        defaultActiveKey={categories}
        items={categories.map((cat) => {
          const catCodes = byCategory[cat].map((p) => p.code);
          const checkedInCat = catCodes.filter((c) => checked.includes(c));
          const allChecked = checkedInCat.length === catCodes.length;
          const indeterminate = checkedInCat.length > 0 && !allChecked;
          return {
            key: cat,
            label: (
              <Space>
                <Checkbox
                  checked={allChecked}
                  indeterminate={indeterminate}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onCategoryToggle(cat, e.target.checked)}
                />
                <Tag color="purple">{cat}</Tag>
                <Text type="secondary">{checkedInCat.length}/{catCodes.length}</Text>
              </Space>
            ),
            children: (
              <Checkbox.Group
                value={checked.filter((c) => catCodes.includes(c))}
                onChange={(vals) => {
                  // 用 vals 替换该 cat 的 checked
                  setChecked((prev) => [
                    ...prev.filter((c) => !catCodes.includes(c)),
                    ...(vals as string[]),
                  ]);
                }}
                className="grid grid-cols-2 gap-y-1"
              >
                {byCategory[cat].map((p) => (
                  <Checkbox key={p.code} value={p.code} className="!mr-0">
                    <span className="font-mono text-xs">{p.code}</span>
                    <Text type="secondary" className="!ml-2">{p.name}</Text>
                  </Checkbox>
                ))}
              </Checkbox.Group>
            ),
          };
        })}
      />
    </Modal>
  );
}
