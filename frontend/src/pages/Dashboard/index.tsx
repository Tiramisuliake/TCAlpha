import { Card } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export default function Dashboard() {
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/health")).data,
  });
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card title="后端状态" className="lg:col-span-1">
        <pre className="text-xs">{JSON.stringify(data, null, 2)}</pre>
      </Card>
      <Card title="今日行情" className="lg:col-span-2">
        <div className="text-slate-400 text-sm">Phase 2 接入实时行情</div>
      </Card>
    </div>
  );
}
