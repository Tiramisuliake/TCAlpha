import { Layout, Menu } from "antd";
import { Link, Outlet, Route, Routes } from "react-router";
import {
  AppstoreOutlined,
  BellOutlined,
  LineChartOutlined,
  RobotOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import Chart from "./pages/Chart";
import Strategy from "./pages/Strategy";
import Backtest from "./pages/Backtest";
import DataMgr from "./pages/Data";
import AI from "./pages/AI";
import Notify from "./pages/Notify";
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
  { key: "data", icon: <DatabaseOutlined />, label: "数据管理" },
  { key: "ai", icon: <RobotOutlined />, label: "AI 助手" },
  { key: "notify", icon: <BellOutlined />, label: "通知中心" },
];

function Shell() {
  const activeKey = useWorkspaceStore((s) => s.activeKey);

  return (
    <Layout className="min-h-screen">
      <Header className="!bg-slate-900 !h-15 flex items-center !px-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-500 text-white font-bold flex items-center justify-center text-sm tracking-wide shadow-sm">
            TC
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-slate-50 font-semibold text-base">TCAlpha</span>
            <span className="text-blue-200/80 text-xs">A 股量化工作台</span>
          </div>
        </div>
      </Header>
      <Layout>
        <Sider
          width={220}
          theme="dark"
          className="!bg-slate-900 border-r border-slate-800"
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
        <Layout className="!bg-slate-50">
          <WorkspaceTabs />
          <Content className="flex flex-col p-6 overflow-auto">
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
      <Route element={<Shell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chart" element={<Chart />} />
        <Route path="/strategy" element={<Strategy />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/data" element={<DataMgr />} />
        <Route path="/ai" element={<AI />} />
        <Route path="/notify" element={<Notify />} />
      </Route>
    </Routes>
  );
}
