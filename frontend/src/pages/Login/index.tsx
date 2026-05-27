import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Typography, message } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router";
import axios from "axios";
import { useAuthStore } from "@/store/useAuthStore";

const { Title, Paragraph } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export default function Login() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fromPath = params.get("from") || "/";
  const login = useAuthStore((s) => s.login);
  const tokenInStore = useAuthStore((s) => s.token);

  // 已登录跳走
  useEffect(() => {
    if (tokenInStore) navigate(fromPath, { replace: true });
  }, [tokenInStore, fromPath, navigate]);

  const submit = async ({ username, password }: LoginForm) => {
    setLoading(true);
    try {
      const token = btoa(`${username}:${password}`);
      // 用 /health 探活 + 凭证校验（这条会过中间件验证）
      const probe = await axios.get("/api/notify/event-types", {
        headers: { Authorization: `Basic ${token}` },
        validateStatus: () => true,
      });
      if (probe.status === 401) {
        message.error("用户名或密码错误");
        return;
      }
      if (probe.status >= 400) {
        message.error(`登录探活失败：HTTP ${probe.status}`);
        return;
      }
      login(username, password);
      message.success("登录成功");
      navigate(fromPath, { replace: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen flex items-center justify-center bg-slate-900 px-4">
      <Card className="w-full max-w-sm shadow-xl">
        <div className="flex flex-col items-center mb-4">
          <div className="w-12 h-12 rounded-xl bg-blue-500 text-white font-bold flex items-center justify-center text-base tracking-wide mb-2">
            TC
          </div>
          <Title level={4} className="!mb-1">
            TCAlpha 登录
          </Title>
          <Paragraph type="secondary" className="!text-xs !mb-0">
            A 股量化工作台 · 使用 .env 中配置的账号
          </Paragraph>
        </div>

        <Form<LoginForm>
          layout="vertical"
          onFinish={submit}
          initialValues={{ username: "admin" }}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              autoComplete="current-password"
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            className="!w-full"
          >
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
