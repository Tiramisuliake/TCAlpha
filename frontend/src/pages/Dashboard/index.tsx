import { Card, Statistic, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { root } from "@/api/client";
import { getSymbols } from "@/api/market";

export default function Dashboard() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => root.get("/health").then((r) => r.data as { status: string; env: string; version: string }),
    refetchInterval: 30_000,
  });

  const { data: symbolsResp } = useQuery({
    queryKey: ["symbols", { limit: 1 }],
    queryFn: () => getSymbols({ limit: 1 }),
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <Statistic
            title="后端状态"
            value={health?.status ?? "—"}
            formatter={(v) => (
              <Tag color={v === "ok" ? "green" : "red"}>{String(v).toUpperCase()}</Tag>
            )}
          />
          <div className="text-xs text-slate-400 mt-1">v{health?.version} · {health?.env}</div>
        </Card>
        <Card>
          <Statistic title="股票数量" value={symbolsResp?.total ?? 0} suffix="只" />
          <div className="text-xs text-slate-400 mt-1">已入库股票总数</div>
        </Card>
        <Card>
          <Statistic title="当前阶段" value="Phase 2" />
          <div className="text-xs text-slate-400 mt-1">前端布局 + K 线图</div>
        </Card>
      </div>

      <Card title="今日行情" className="min-h-40">
        <div className="text-slate-400 text-sm flex items-center justify-center h-24">
          Phase 3 接入实时行情推送
        </div>
      </Card>
    </div>
  );
}
