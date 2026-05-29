import { useEffect, useState } from "react";
import { App, Button, Card, Form, Input, Typography } from "antd";
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
  const accessToken = useAuthStore((s) => s.accessToken);
  // hook 版 message：保证读取到 AntD ConfigProvider 上下文
  const { message } = App.useApp();

  useEffect(() => {
    if (accessToken) navigate(fromPath, { replace: true });
  }, [accessToken, fromPath, navigate]);

  const submit = async ({ username, password }: LoginForm) => {
    setLoading(true);
    try {
      await login(username, password);
      message.success("登录成功");
      navigate(fromPath, { replace: true });
    } catch (err) {
      // 细分错误分类，避免"没有任何反馈"
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        const detail =
          (err.response?.data as { detail?: string } | undefined)?.detail ?? "";

        if (status === 401) {
          message.error("用户名或密码错误");
        } else if (status === 422) {
          message.error("用户名/密码格式不合法");
        } else if (status && status >= 500) {
          message.error(`后端异常 (HTTP ${status})，请稍后重试`);
        } else if (status) {
          message.error(detail || `登录失败 (HTTP ${status})`);
        } else if (err.code === "ERR_NETWORK") {
          message.error(
            "无法连接后端服务，请确认 backend 已启动 (uvicorn 默认 8000 端口)",
          );
        } else if (err.code === "ECONNABORTED") {
          message.error("登录超时，请检查网络");
        } else {
          message.error(err.message || "登录失败");
        }
      } else {
        message.error((err as Error)?.message || "登录失败");
      }
      // 同步把表单标红，给字段级反馈
      // 不清密码，方便用户修正
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
            A 股量化工作台
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
