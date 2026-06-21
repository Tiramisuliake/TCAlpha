import type { ReactNode } from "react";
import { Card, Statistic, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import {
  AlertOutlined,
  DatabaseOutlined,
  DollarOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { root } from "@/api/client";
import { getDataHealth, getSymbols } from "@/api/market";
import { getAccount } from "@/api/sim";
import { listAlerts } from "@/api/ai_alerts";
import { useAuthStore } from "@/store/useAuthStore";

interface Shortcut {
  to: string;
  label: string;
  desc: string;
  icon: ReactNode;
  perm?: string;
}

const SHORTCUTS: Shortcut[] = [
  { to: "/chart", label: "K 线分析", desc: "行情图表 + AI 解读", icon: <LineChartOutlined /> },
  { to: "/strategy", label: "策略管理", desc: "创建 / 运行策略", icon: <ThunderboltOutlined />, perm: "strategy.read" },
  { to: "/backtest", label: "回测", desc: "历史数据验证策略", icon: <ExperimentOutlined />, perm: "backtest.read" },
  { to: "/trade", label: "模拟交易", desc: "下单 / 持仓 / 订单", icon: <DollarOutlined />, perm: "sim.order.read" },
  { to: "/data", label: "数据管理", desc: "下载 K 线数据", icon: <DatabaseOutlined />, perm: "data.read" },
  { to: "/ai", label: "AI 助手", desc: "智能问答助手", icon: <RobotOutlined />, perm: "ai.chat" },
];

export default function Dashboard() {
  const has = useAuthStore((s) => s.has);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      root.get("/health").then((r) => r.data as { status: string; env: string; version: string }),
    refetchInterval: 30_000,
  });

  const { data: symbolsResp } = useQuery({
    queryKey: ["symbols", { limit: 1 }],
    queryFn: () => getSymbols({ limit: 1 }),
  });

  const canData = has("data.read");
  const canSim = has("sim.order.read");
  const canWatch = has("ai.watch");

  // ── 运行概览：仅在有对应权限时拉取，避免无权限触发 403 ──
  const { data: dataHealth } = useQuery({
    queryKey: ["dashboard-data-health"],
    queryFn: getDataHealth,
    enabled: canData,
    staleTime: 60_000,
  });

  const { data: account } = useQuery({
    queryKey: ["dashboard-account"],
    queryFn: getAccount,
    enabled: canSim,
    staleTime: 30_000,
  });

  const { data: alerts } = useQuery({
    queryKey: ["dashboard-alerts"],
    queryFn: () => listAlerts({ only_unacked: true, limit: 50 }),
    enabled: canWatch,
    refetchInterval: 60_000,
  });

  const shortcuts = SHORTCUTS.filter((s) => !s.perm || has(s.perm));
  const showOverview = canData || canSim || canWatch;

  const pnl = account ? account.total_asset - account.init_capital : 0;
  const latestAlert = alerts?.[0];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-auto">
      {/* 系统状态 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card>
          <Statistic
            title="后端状态"
            value={health?.status ?? "—"}
            formatter={(v) => (
              <Tag color={v === "ok" ? "green" : "red"}>{String(v).toUpperCase()}</Tag>
            )}
          />
          <div className="text-xs text-slate-400 mt-1">实时健康检查（30s 轮询）</div>
        </Card>
        <Card>
          <Statistic title="股票数量" value={symbolsResp?.total ?? 0} suffix="只" />
          <div className="text-xs text-slate-400 mt-1">已入库股票总数</div>
        </Card>
        <Card>
          <Statistic title="系统版本" value={health?.version ? `v${health.version}` : "—"} />
          <div className="text-xs text-slate-400 mt-1">运行环境：{health?.env ?? "—"}</div>
        </Card>
      </div>

      {/* 运行概览（按权限聚合数据健康 / 模拟账户 / AI 告警，点击跳转对应页） */}
      {showOverview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {canData && (
            <Link to="/data" className="block">
              <Card hoverable size="small">
                <Statistic
                  title={
                    <span>
                      <DatabaseOutlined /> 数据覆盖率
                    </span>
                  }
                  value={dataHealth ? dataHealth.coverage_rate * 100 : 0}
                  precision={1}
                  suffix="%"
                  valueStyle={{
                    color: dataHealth && dataHealth.coverage_rate < 0.8 ? "#f59e0b" : undefined,
                  }}
                />
                <div className="text-xs text-slate-400 mt-1">
                  已覆盖 {dataHealth?.bar1d_covered ?? 0}/{dataHealth?.symbols_total ?? 0} 只
                  {dataHealth && dataHealth.sync_failed > 0 && (
                    <span className="text-red-500"> · 同步失败 {dataHealth.sync_failed}</span>
                  )}
                </div>
              </Card>
            </Link>
          )}
          {canSim && (
            <Link to="/trade" className="block">
              <Card hoverable size="small">
                <Statistic
                  title={
                    <span>
                      <DollarOutlined /> 模拟总资产
                    </span>
                  }
                  value={account?.total_asset ?? 0}
                  precision={2}
                  valueStyle={{ color: pnl >= 0 ? "#ef4444" : "#10b981" }}
                />
                <div className="text-xs text-slate-400 mt-1">
                  浮动盈亏{" "}
                  <span className={pnl >= 0 ? "text-red-500" : "text-emerald-500"}>
                    {pnl >= 0 ? "+" : ""}
                    {pnl.toFixed(2)}
                  </span>
                </div>
              </Card>
            </Link>
          )}
          {canWatch && (
            <Link to="/monitor" className="block">
              <Card hoverable size="small">
                <Statistic
                  title={
                    <span>
                      <AlertOutlined /> 未读告警
                    </span>
                  }
                  value={alerts?.length ?? 0}
                  suffix="条"
                  valueStyle={{ color: alerts && alerts.length > 0 ? "#f59e0b" : undefined }}
                />
                <div className="text-xs text-slate-400 mt-1 truncate">
                  {latestAlert
                    ? `最新：${latestAlert.symbol} ${latestAlert.signal}`
                    : "暂无未读告警"}
                </div>
              </Card>
            </Link>
          )}
        </div>
      )}

      {/* 功能入口 */}
      <Card title="功能入口" className="flex-1 min-h-0">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {shortcuts.map((s) => (
            <Link key={s.to} to={s.to}>
              <div className="flex items-center gap-3 p-3 border border-[var(--tc-border)] rounded hover:bg-[var(--tc-bg-elevated)] transition-colors">
                <span className="text-xl text-[var(--tc-primary)]">{s.icon}</span>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-slate-800">{s.label}</span>
                  <span className="text-xs text-slate-400">{s.desc}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
