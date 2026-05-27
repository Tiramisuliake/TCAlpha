import { useState } from "react";
import {
  Button,
  Card,
  Empty,
  Segmented,
  Space,
  Switch,
  Tag,
  Tooltip,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  ackAlert,
  listAlerts,
  type AiAlert,
  type AlertLevel,
} from "@/api/ai_alerts";

const LEVEL_META: Record<AlertLevel, { color: string; label: string }> = {
  info: { color: "blue", label: "info" },
  warn: { color: "orange", label: "warn" },
  danger: { color: "red", label: "danger" },
};

export default function AlertList() {
  const qc = useQueryClient();
  const [filterLevel, setFilterLevel] = useState<AlertLevel | "all">("all");
  const [onlyUnacked, setOnlyUnacked] = useState(false);

  const { data = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["ai-alerts", filterLevel, onlyUnacked],
    queryFn: () =>
      listAlerts({
        level: filterLevel === "all" ? undefined : filterLevel,
        only_unacked: onlyUnacked || undefined,
        limit: 100,
      }),
    staleTime: 10_000,
  });

  const ackMut = useMutation({
    mutationFn: ackAlert,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-alerts"] });
    },
    onError: () => message.error("标记失败"),
  });

  return (
    <div className="flex flex-col gap-3 min-h-0 flex-1">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <Space size="middle">
          <Segmented
            value={filterLevel}
            onChange={(v) => setFilterLevel(v as AlertLevel | "all")}
            options={[
              { label: "全部", value: "all" },
              { label: "info", value: "info" },
              { label: "warn", value: "warn" },
              { label: "danger", value: "danger" },
            ]}
          />
          <span className="text-sm text-slate-500">
            <Switch
              size="small"
              checked={onlyUnacked}
              onChange={setOnlyUnacked}
              className="!mr-2"
            />
            只看未读
          </span>
        </Space>
        <Tooltip title="刷新">
          <Button
            icon={<ReloadOutlined />}
            loading={isFetching}
            onClick={() => refetch()}
          />
        </Tooltip>
      </div>

      <div className="flex-1 overflow-y-auto pr-1 space-y-3 min-h-0">
        {!isLoading && data.length === 0 ? (
          <Empty
            description={
              onlyUnacked
                ? "没有未读告警"
                : "暂无 AI 盯盘告警。请先在「关注列表」添加股票，并启动 Celery worker + beat。"
            }
          />
        ) : (
          data.map((a) => (
            <AlertCard
              key={a.id}
              alert={a}
              onAck={() => ackMut.mutate(a.id)}
              acking={ackMut.isPending && ackMut.variables === a.id}
            />
          ))
        )}
      </div>
    </div>
  );
}

function AlertCard({
  alert,
  onAck,
  acking,
}: {
  alert: AiAlert;
  onAck: () => void;
  acking: boolean;
}) {
  const meta = LEVEL_META[alert.level] ?? LEVEL_META.info;
  return (
    <Card
      size="small"
      className={alert.acked ? "opacity-70" : ""}
      classNames={{ body: "flex flex-col gap-2" }}
    >
      <div className="flex items-center justify-between gap-2">
        <Space size="small" wrap>
          <Tag color={meta.color}>{meta.label.toUpperCase()}</Tag>
          <Tag color="geekblue">{alert.symbol}</Tag>
          <span className="text-xs text-slate-400">
            {alert.created_at.replace("T", " ").split(".")[0]}
          </span>
          {alert.acked && <Tag>已读</Tag>}
        </Space>
        {!alert.acked && (
          <Button
            size="small"
            icon={<CheckOutlined />}
            loading={acking}
            onClick={onAck}
          >
            标已读
          </Button>
        )}
      </div>
      <div className="text-sm text-slate-800 font-medium">{alert.signal}</div>
      <div className="text-sm text-slate-600 whitespace-pre-wrap leading-6">
        {alert.reason}
      </div>
      <details className="text-xs text-slate-500">
        <summary className="cursor-pointer select-none hover:text-slate-700">
          指标快照
        </summary>
        <pre className="mt-2 bg-slate-50 rounded p-2 overflow-auto text-[11px] leading-5">
          {JSON.stringify(alert.snapshot, null, 2)}
        </pre>
      </details>
    </Card>
  );
}
