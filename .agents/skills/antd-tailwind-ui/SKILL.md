---
name: antd-tailwind-ui
description: Ant Design 5 组件 + TailwindCSS 4 布局 / 表单 / 表格 / 弹窗 / Drawer。触发词：AntD、Ant Design、Tailwind、UI、组件、表单、表格、弹窗、布局、样式、CSS
---

# Ant Design 5 + Tailwind 4

## 分工

- **AntD**：复杂控件（Form / Table / DatePicker / Modal / Select…）
- **Tailwind**：布局（flex / grid / spacing）、间距、颜色、文字

不要自己写 Modal / Form Validation / Table 分页这些 AntD 已有的；不要写复杂自定义 CSS（先试 Tailwind class）。

## 项目已注入

- `ConfigProvider locale={zhCN}` 在 `main.tsx` 顶层（中文 DatePicker、Pagination 等）
- Tailwind v4 通过 `@import "tailwindcss"` 在 `styles/index.css` 加载
- AntD 5 用 reset.css 自动，不需要额外引入

## 布局

```tsx
<div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
  <Card>左</Card>
  <Card className="lg:col-span-2">右</Card>
</div>

<div className="flex items-center justify-between gap-2">
  <Title level={3}>策略管理</Title>
  <Button type="primary">新建</Button>
</div>
```

## 表单

```tsx
import { Form, Input, InputNumber, Select, Button } from "antd";

const [form] = Form.useForm();

<Form form={form} layout="vertical" onFinish={onSubmit}>
  <Form.Item label="名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
    <Input />
  </Form.Item>
  <Form.Item label="股票" name="symbol" rules={[{ required: true }]}>
    <Select options={symbolOptions} showSearch />
  </Form.Item>
  <Form.Item label="快线周期" name="fast" rules={[{ required: true, type: "number" }]}>
    <InputNumber min={2} max={200} className="!w-full" />
  </Form.Item>
  <Button type="primary" htmlType="submit">提交</Button>
</Form>
```

注意：AntD class 优先级高于 Tailwind 时用 `!` 前缀强制（如 `!w-full`）。

## 表格

```tsx
import { Table, Tag, Space, Button } from "antd";
import type { ColumnsType } from "antd/es/table";

const cols: ColumnsType<Strategy> = [
  { title: "名称", dataIndex: "name", key: "name" },
  { title: "股票", dataIndex: "symbol", key: "symbol", width: 100 },
  {
    title: "状态",
    dataIndex: "status",
    render: (s) => <Tag color={s === "running" ? "green" : "default"}>{s}</Tag>,
  },
  {
    title: "操作",
    key: "actions",
    render: (_, row) => (
      <Space>
        <Button size="small" onClick={() => onEdit(row)}>编辑</Button>
        <Button size="small" danger onClick={() => onDelete(row.id)}>删除</Button>
      </Space>
    ),
  },
];

<Table dataSource={items} columns={cols} rowKey="id" pagination={{ pageSize: 10 }} />
```

## Modal 确认

```tsx
import { Modal } from "antd";

Modal.confirm({
  title: "确认删除",
  content: "删除后不可恢复",
  okText: "删除",
  cancelText: "取消",
  okType: "danger",
  onOk: () => deleteItem(id),
});
```

不可逆操作必须用 `Modal.confirm`。

## Drawer 适合编辑详情

```tsx
<Drawer open={open} onClose={onClose} title="编辑策略" width={520}>
  <Form ... />
</Drawer>
```

## 消息提示

```tsx
import { message } from "antd";
message.success("保存成功");
message.error("失败：" + err);
message.info("…");
```

axios 拦截器已统一报错，组件层只在业务成功路径用 `message.success`。

## 颜色 / 间距规范

- 主色：AntD 默认蓝（不要轻易改）
- 涨绿跌红（A 股习惯）：自定义类 `text-red-500` / `text-green-500`
- 间距：`gap-2 / gap-4 / gap-6 / gap-8`
- 圆角：`rounded` / `rounded-lg`
- 阴影：`shadow-sm` / `shadow`

## Tailwind v4 注意

- 不需要 `tailwind.config.js` 主体，content 走 `@import` 自动扫描
- 但 PostCSS 配置用 `@tailwindcss/postcss`，已配
- 旧版 `@apply` 在 v4 仍支持但不推荐

## 禁止

- ❌ 内联大段 style（除动态计算）
- ❌ 自己写 Modal / Pagination / DatePicker
- ❌ 直接修改 antd 组件内部 class（用 token / theme 配）
- ❌ 引第三方 UI 库（Material / Chakra）混用
