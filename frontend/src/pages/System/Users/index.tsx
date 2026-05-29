import { useState } from "react";
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  Space,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  KeyOutlined,
  PlusOutlined,
  SafetyOutlined,
  UsergroupAddOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import {
  createUser,
  deleteUser,
  listRoles,
  listUsers,
  resetUserPassword,
  setUserRoles,
  updateUser,
} from "@/api/system";
import type { RoleOut, UserCreate, UserListItem } from "@/types";
import { useAuthStore } from "@/store/useAuthStore";

const { Title } = Typography;

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; user: UserListItem }
  | { kind: "roles"; user: UserListItem }
  | { kind: "password"; user: UserListItem };

export default function SystemUsersPage() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.me);

  const { data: users, isLoading } = useQuery({
    queryKey: ["system", "users"],
    queryFn: listUsers,
  });

  const { data: roles } = useQuery({
    queryKey: ["system", "roles"],
    queryFn: listRoles,
  });

  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const close = () => setModal({ kind: "closed" });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["system", "users"] });

  const createMut = useMutation({
    mutationFn: (p: UserCreate) => createUser(p),
    onSuccess: () => {
      message.success("用户已创建");
      invalidate();
      close();
    },
  });

  const updateMut = useMutation({
    mutationFn: (vars: { id: number; payload: Parameters<typeof updateUser>[1] }) =>
      updateUser(vars.id, vars.payload),
    onSuccess: () => {
      message.success("用户已更新");
      invalidate();
      close();
    },
  });

  const rolesMut = useMutation({
    mutationFn: (vars: { id: number; role_codes: string[] }) =>
      setUserRoles(vars.id, vars.role_codes),
    onSuccess: () => {
      message.success("角色已更新");
      invalidate();
      close();
    },
  });

  const pwdMut = useMutation({
    mutationFn: (vars: { id: number; new_password: string }) =>
      resetUserPassword(vars.id, vars.new_password),
    onSuccess: () => {
      message.success("密码已重置");
      close();
    },
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteUser(id),
    onSuccess: () => {
      message.success("用户已删除");
      invalidate();
    },
  });

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "用户名", dataIndex: "username", width: 140 },
    { title: "显示名", dataIndex: "display_name", width: 160 },
    {
      title: "邮箱",
      dataIndex: "email",
      width: 200,
      render: (v: string | null) => v || "—",
    },
    {
      title: "角色",
      dataIndex: "role_codes",
      render: (codes: string[]) =>
        codes.length === 0
          ? "—"
          : codes.map((c) => <Tag key={c}>{c}</Tag>),
    },
    {
      title: "状态",
      dataIndex: "is_active",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag>,
    },
    {
      title: "超管",
      dataIndex: "is_super",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag icon={<SafetyOutlined />} color="gold">SUPER</Tag> : "—",
    },
    {
      title: "上次登录",
      dataIndex: "last_login_at",
      width: 160,
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "—"),
    },
    {
      title: "操作",
      width: 280,
      fixed: "right" as const,
      render: (_: unknown, u: UserListItem) => (
        <Space size="small">
          <Tooltip title="编辑基本资料">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => setModal({ kind: "edit", user: u })}
            />
          </Tooltip>
          <Tooltip title="分配角色">
            <Button
              size="small"
              icon={<UsergroupAddOutlined />}
              onClick={() => setModal({ kind: "roles", user: u })}
            />
          </Tooltip>
          <Tooltip title="重置密码">
            <Button
              size="small"
              icon={<KeyOutlined />}
              onClick={() => setModal({ kind: "password", user: u })}
            />
          </Tooltip>
          <Popconfirm
            title={`删除用户 ${u.username} ？`}
            description="此操作不可撤销。"
            onConfirm={() => delMut.mutate(u.id)}
            disabled={u.id === me?.id}
          >
            <Tooltip
              title={
                u.id === me?.id ? "不能删除自己" : "删除用户"
              }
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={u.id === me?.id}
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
        title={<Title level={5} className="!mb-0">用户管理</Title>}
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModal({ kind: "create" })}
          >
            新建用户
          </Button>
        }
      >
        <Table<UserListItem>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={users || []}
          columns={columns}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <CreateModal
        open={modal.kind === "create"}
        roles={roles || []}
        loading={createMut.isPending}
        onCancel={close}
        onSubmit={(payload) => createMut.mutate(payload)}
      />

      <EditModal
        open={modal.kind === "edit"}
        user={modal.kind === "edit" ? modal.user : null}
        loading={updateMut.isPending}
        onCancel={close}
        onSubmit={(payload) =>
          modal.kind === "edit" &&
          updateMut.mutate({ id: modal.user.id, payload })
        }
      />

      <RolesModal
        open={modal.kind === "roles"}
        user={modal.kind === "roles" ? modal.user : null}
        roles={roles || []}
        loading={rolesMut.isPending}
        onCancel={close}
        onSubmit={(role_codes) =>
          modal.kind === "roles" &&
          rolesMut.mutate({ id: modal.user.id, role_codes })
        }
      />

      <PasswordModal
        open={modal.kind === "password"}
        user={modal.kind === "password" ? modal.user : null}
        loading={pwdMut.isPending}
        onCancel={close}
        onSubmit={(new_password) =>
          modal.kind === "password" &&
          pwdMut.mutate({ id: modal.user.id, new_password })
        }
      />
    </div>
  );
}

// ── 子 Modal ──────────────────────────────────────────────

function CreateModal(props: {
  open: boolean;
  roles: RoleOut[];
  loading: boolean;
  onCancel: () => void;
  onSubmit: (p: UserCreate) => void;
}) {
  const [form] = Form.useForm<UserCreate>();
  return (
    <Modal
      title="新建用户"
      open={props.open}
      onCancel={props.onCancel}
      onOk={() => form.submit()}
      confirmLoading={props.loading}
      destroyOnHidden
      forceRender
    >
      <Form<UserCreate>
        form={form}
        layout="vertical"
        initialValues={{ is_active: true, is_super: false, role_codes: [] }}
        onFinish={(v) => props.onSubmit(v)}
      >
        <Form.Item label="用户名" name="username" rules={[{ required: true, max: 64 }]}>
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, min: 6, message: "至少 6 位" }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="显示名" name="display_name">
          <Input />
        </Form.Item>
        <Form.Item label="邮箱" name="email">
          <Input type="email" />
        </Form.Item>
        <Form.Item label="角色" name="role_codes">
          <Select
            mode="multiple"
            placeholder="选择角色"
            options={props.roles.map((r) => ({ value: r.code, label: `${r.name} (${r.code})` }))}
          />
        </Form.Item>
        <Form.Item label="启用" name="is_active" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label="超级管理员" name="is_super" valuePropName="checked" tooltip="绕过所有权限检查">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function EditModal(props: {
  open: boolean;
  user: UserListItem | null;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (p: { display_name?: string; email?: string | null; is_active?: boolean }) => void;
}) {
  const [form] = Form.useForm();
  return (
    <Modal
      title={`编辑用户  ${props.user?.username ?? ""}`}
      open={props.open}
      onCancel={props.onCancel}
      onOk={() => form.submit()}
      confirmLoading={props.loading}
      destroyOnHidden
      forceRender
    >
      {props.user && (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            display_name: props.user.display_name,
            email: props.user.email,
            is_active: props.user.is_active,
          }}
          onFinish={(v) => props.onSubmit(v)}
        >
          <Form.Item label="显示名" name="display_name">
            <Input />
          </Form.Item>
          <Form.Item label="邮箱" name="email">
            <Input type="email" />
          </Form.Item>
          <Form.Item label="启用" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function RolesModal(props: {
  open: boolean;
  user: UserListItem | null;
  roles: RoleOut[];
  loading: boolean;
  onCancel: () => void;
  onSubmit: (codes: string[]) => void;
}) {
  const [form] = Form.useForm<{ role_codes: string[] }>();
  return (
    <Modal
      title={`分配角色  ${props.user?.username ?? ""}`}
      open={props.open}
      onCancel={props.onCancel}
      onOk={() => form.submit()}
      confirmLoading={props.loading}
      destroyOnHidden
      forceRender
    >
      {props.user && (
        <Form
          form={form}
          layout="vertical"
          initialValues={{ role_codes: props.user.role_codes }}
          onFinish={(v) => props.onSubmit(v.role_codes ?? [])}
        >
          <Form.Item label="角色（多选）" name="role_codes">
            <Select
              mode="multiple"
              placeholder="选择角色"
              options={props.roles.map((r) => ({
                value: r.code,
                label: `${r.name} (${r.code})`,
              }))}
            />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function PasswordModal(props: {
  open: boolean;
  user: UserListItem | null;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (new_password: string) => void;
}) {
  const [form] = Form.useForm<{ new_password: string; confirm: string }>();
  return (
    <Modal
      title={`重置密码  ${props.user?.username ?? ""}`}
      open={props.open}
      onCancel={props.onCancel}
      onOk={() => form.submit()}
      confirmLoading={props.loading}
      destroyOnHidden
      forceRender
    >
      {props.user && (
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => props.onSubmit(v.new_password)}
        >
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[{ required: true, min: 6, message: "至少 6 位" }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirm"
            dependencies={["new_password"]}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, v) {
                  if (!v || v === getFieldValue("new_password")) return Promise.resolve();
                  return Promise.reject(new Error("两次输入不一致"));
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
