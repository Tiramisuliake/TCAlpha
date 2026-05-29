import { useEffect } from "react";
import { Dropdown, Layout, Menu, Spin } from "antd";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router";
import { useAuthStore } from "@/store/useAuthStore";
import {
  AppstoreOutlined,
  BellOutlined,
  DollarOutlined,
  LineChartOutlined,
  LogoutOutlined,
  RobotOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import Chart from "./pages/Chart";
import Strategy from "./pages/Strategy";
import Backtest from "./pages/Backtest";
import Trade from "./pages/Trade";
import DataMgr from "./pages/Data";
import AI from "./pages/AI";
import Notify from "./pages/Notify";
import Login from "./pages/Login";
import { WorkspaceTabs } from "./components/WorkspaceTabs";
import {
  useWorkspaceStore,
  WORKSPACE_ROUTES,
  type WorkspaceRouteKey,
} from "./store/useWorkspaceStore";

const { Header, Content, Sider } = Layout;

const MENU_ITEMS: { key: WorkspaceRouteKey; icon: React.ReactNode; label: string }[] = [
  { key: "dashboard", icon: <AppstoreOutlined />, label: "仪表盘" },
  { key: "chart", icon: <LineChartOutlined />, label: "K 线分析" },
  { key: "strategy", icon: <ThunderboltOutlined />, label: "策略管理" },
  { key: "backtest", icon: <ExperimentOutlined />, label: "回测" },
  { key: "trade", icon: <DollarOutlined />, label: "模拟交易" },
  { key: "data", icon: <DatabaseOutlined />, label: "数据管理" },
  { key: "ai", icon: <RobotOutlined />, label: "AI 助手" },
  { key: "notify", icon: <BellOutlined />, label: "通知中心" },
];

function RequireAuth({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const bootstrapping = useAuthStore((s) => s.bootstrapping);
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const location = useLocation();

  useEffect(() => {
    // 启动时尝试用 refresh cookie 静默恢复登录态
    bootstrap();
  }, [bootstrap]);

  if (bootstrapping) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-900">
        <Spin tip="正在恢复登录态…" />
      </div>
    );
  }
  if (!accessToken) {
    return <Navigate to={`/login?from=${encodeURIComponent(location.pathname)}`} replace />;
  }
  return <>{children}</>;
}

function UserMenu() {
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const displayName = me?.display_name || me?.username || "用户";
  const tag = me?.is_super ? "超级管理员" : me?.roles?.[0] ?? "";

  return (
    <Dropdown
      menu={{
        items: [
          {
            key: "logout",
            icon: <LogoutOutlined />,
            label: "退出登录",
            onClick: onLogout,
          },
        ],
      }}
      placement="bottomRight"
    >
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer hover:bg-slate-800">
        <UserOutlined className="text-slate-300" />
        <div className="flex flex-col leading-tight">
          <span className="text-slate-100 text-sm">{displayName}</span>
          {tag && <span className="text-slate-400 text-xs">{tag}</span>}
        </div>
      </div>
    </Dropdown>
  );
}

function Shell() {
  const activeKey = useWorkspaceStore((s) => s.activeKey);

  return (
    <Layout className="h-screen overflow-hidden">
      <Header className="!bg-slate-900 !h-15 flex-shrink-0 flex items-center justify-between !px-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-500 text-white font-bold flex items-center justify-center text-sm tracking-wide shadow-sm">
            TC
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-slate-50 font-semibold text-base">TCAlpha</span>
            <span className="text-blue-200/80 text-xs">A 股量化工作台</span>
          </div>
        </div>
        <UserMenu />
      </Header>
      <Layout className="flex-1 min-h-0">
        <Sider
          width={220}
          theme="dark"
          className="!bg-slate-900 border-r border-slate-800 overflow-y-auto"
        >
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[activeKey]}
            className="!bg-transparent !border-r-0 !pt-3 px-2"
            items={MENU_ITEMS.map((m) => ({
              key: m.key,
              icon: m.icon,
              label: <Link to={WORKSPACE_ROUTES[m.key].path}>{m.label}</Link>,
            }))}
          />
        </Sider>
        <Layout className="!bg-slate-100 flex-1 min-w-0 flex flex-col">
          <WorkspaceTabs />
          <Content className="flex-1 min-h-0 p-4 overflow-hidden flex flex-col">
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/chart" element={<Chart />} />
        <Route path="/strategy" element={<Strategy />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/trade" element={<Trade />} />
        <Route path="/data" element={<DataMgr />} />
        <Route path="/ai" element={<AI />} />
        <Route path="/notify" element={<Notify />} />
      </Route>
    </Routes>
  );
}
