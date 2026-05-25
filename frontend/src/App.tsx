import { Layout, Menu } from "antd";
import { Link, Outlet, Route, Routes } from "react-router";
import {
  AppstoreOutlined,
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

const { Header, Content, Sider } = Layout;

function Shell() {
  return (
    <Layout className="min-h-screen">
      <Header className="!bg-slate-900 text-white flex items-center px-6">
        <span className="text-lg font-bold">TCAlpha · A 股量化</span>
      </Header>
      <Layout>
        <Sider width={200} className="!bg-slate-50">
          <Menu
            mode="inline"
            defaultSelectedKeys={["dashboard"]}
            className="!h-full !border-r-0"
            items={[
              { key: "dashboard", icon: <AppstoreOutlined />, label: <Link to="/">仪表盘</Link> },
              { key: "chart", icon: <LineChartOutlined />, label: <Link to="/chart">K 线分析</Link> },
              { key: "strategy", icon: <ThunderboltOutlined />, label: <Link to="/strategy">策略管理</Link> },
              { key: "backtest", icon: <ExperimentOutlined />, label: <Link to="/backtest">回测</Link> },
              { key: "data", icon: <DatabaseOutlined />, label: <Link to="/data">数据管理</Link> },
              { key: "ai", icon: <RobotOutlined />, label: <Link to="/ai">AI 助手</Link> },
            ]}
          />
        </Sider>
        <Content className="p-6 bg-white">
          <Outlet />
        </Content>
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
      </Route>
    </Routes>
  );
}
