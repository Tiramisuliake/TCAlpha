import type { ReactNode } from "react";
import { Card, Statistic, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import {
  DatabaseOutlined,
  DollarOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { root } from "@/api/client";
import { getSymbols } from "@/api/market";
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

  const shortcuts = SHORTCUTS.filter((s) => !s.perm || has(s.perm));

  return (
    <div className="flex-1 min-h-0 grid grid-rows-[auto_1fr] gap-3 overflow-auto">
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
