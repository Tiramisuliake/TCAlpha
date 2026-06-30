import { Alert, Card, Empty, Statistic, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { getLimitUpLadder, getSentiment, getSentimentHistory } from "@/api/market";
import type { LimitUpLeader } from "@/types";

const LEADER_COLS: ColumnsType<LimitUpLeader> = [
  { title: "代码", dataIndex: "code", width: 78, render: (v) => <span className="num">{v}</span> },
  { title: "名称", dataIndex: "name" },
  {
    title: "连板",
    dataIndex: "boards",
    align: "right",
    render: (v: number) => <Tag color="red" className="!m-0">{v} 板</Tag>,
  },
];

const UP = "#ef4444";
const DOWN = "#10b981";

/** 温度 → 冷热档位（文案 + 颜色）。 */
function tempLevel(t: number): { text: string; color: string } {
  if (t >= 80) return { text: "过热 · 谨慎追高", color: "red" };
  if (t >= 60) return { text: "偏暖 · 情绪积极", color: "orange" };
  if (t >= 40) return { text: "中性 · 多空均衡", color: "gold" };
  if (t >= 20) return { text: "偏冷 · 情绪低迷", color: "cyan" };
  return { text: "冰点 · 极度恐慌", color: "green" };
}

/**
 * 市场情绪温度计：全市场涨跌停 / 涨跌比 / 赚钱效应聚合大盘冷热（择时维度）。
 * 实时读 spot 快照（60s 刷新）+ 历史温度曲线（收盘 beat 存档）。
 */
export default function Sentiment() {
  const { data: s } = useQuery({
    queryKey: ["market-sentiment"],
    queryFn: getSentiment,
    refetchInterval: 60_000,
  });
  const { data: history } = useQuery({
    queryKey: ["market-sentiment-history"],
    queryFn: () => getSentimentHistory(120),
    staleTime: 5 * 60_000,
  });
  const { data: ladder } = useQuery({
    queryKey: ["limit-up-ladder"],
    queryFn: getLimitUpLadder,
    staleTime: 5 * 60_000,
  });

  const ladderOption =
    ladder?.ready && ladder.ladder.length > 0
      ? {
          tooltip: { trigger: "axis" },
          grid: { left: 34, right: 12, top: 16, bottom: 26 },
          xAxis: { type: "category", data: ladder.ladder.map((b) => b.label) },
          yAxis: { type: "value" },
          series: [
            {
              type: "bar",
              data: ladder.ladder.map((b) => b.count),
              barWidth: "52%",
              itemStyle: { color: "#ef4444" },
              label: { show: true, position: "top", fontSize: 11 },
            },
          ],
        }
      : null;

  const ready = !!s?.ready;
  const temp = s?.temperature ?? 50;
  const level = tempLevel(temp);

  const gaugeOption = {
    series: [
      {
        type: "gauge",
        min: 0,
        max: 100,
        radius: "92%",
        progress: { show: true, width: 14 },
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.2, DOWN],
              [0.4, "#34d399"],
              [0.6, "#fbbf24"],
              [0.8, "#fb923c"],
              [1, UP],
            ],
          },
        },
        axisTick: { show: false },
        splitLine: { length: 10, lineStyle: { width: 2 } },
        axisLabel: { fontSize: 9, distance: 14 },
        pointer: { width: 5 },
        detail: {
          valueAnimation: true,
          formatter: "{value}",
          fontSize: 34,
          fontWeight: "bold",
          offsetCenter: [0, "62%"],
          color: "inherit",
        },
        data: [{ value: temp }],
      },
    ],
  };

  const histOption =
    history && history.length > 0
      ? {
          tooltip: { trigger: "axis" },
          grid: { left: 38, right: 16, top: 16, bottom: 40 },
          xAxis: {
            type: "category",
            data: history.map((p) => p.date),
            axisLabel: { rotate: 30, fontSize: 10 },
          },
          yAxis: { type: "value", min: 0, max: 100 },
          series: [
            {
              type: "line",
              data: history.map((p) => p.temperature),
              smooth: true,
              symbol: "none",
              lineStyle: { color: "#fb923c", width: 2 },
              areaStyle: {
                color: {
                  type: "linear",
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: "rgba(251,146,60,0.3)" },
                    { offset: 1, color: "rgba(251,146,60,0)" },
                  ],
                },
              },
              markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#94a3b8", type: "dashed" },
                data: [{ yAxis: 50 }],
              },
            },
          ],
        }
      : null;

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-auto">
      {s && !ready && (
        <Alert type="info" showIcon message="全市场快照刷新中（需 Celery worker），请稍后；或交易时段数据更实时" />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card size="small" title="市场情绪温度计" className="lg:col-span-1">
          <ReactECharts option={gaugeOption} style={{ height: 220 }} notMerge />
          <div className="text-center -mt-2">
            <Tag color={level.color} className="text-sm">{level.text}</Tag>
          </div>
        </Card>

        <Card size="small" title="涨跌分布（全市场实时）" className="lg:col-span-2">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-y-4">
            <Statistic title="上涨" value={s?.up ?? 0} suffix="家" valueStyle={{ color: UP }} />
            <Statistic title="下跌" value={s?.down ?? 0} suffix="家" valueStyle={{ color: DOWN }} />
            <Statistic title="涨停" value={s?.limit_up ?? 0} suffix="家" valueStyle={{ color: UP }} />
            <Statistic title="跌停" value={s?.limit_down ?? 0} suffix="家" valueStyle={{ color: DOWN }} />
            <Statistic title="平盘" value={s?.flat ?? 0} suffix="家" />
            <Statistic title="涨跌比" value={s?.adv_decline_ratio ?? 0} precision={2} />
            <Statistic
              title="赚钱效应"
              value={(s?.profit_effect ?? 0) * 100}
              precision={1}
              suffix="%"
            />
            <Statistic
              title="平均涨跌"
              value={s?.avg_pct_chg ?? 0}
              precision={2}
              suffix="%"
              valueStyle={{ color: (s?.avg_pct_chg ?? 0) >= 0 ? UP : DOWN }}
            />
          </div>
          <div className="mt-3 text-xs text-slate-400">
            温度 = 上涨家数 / 活跃家数 ×100：&lt;20 冰点、50 多空均衡、&gt;80 过热。择时维度，与选股互补。
          </div>
        </Card>
      </div>

      {ladder?.ready && ladder.total > 0 && (
        <Card
          size="small"
          title="连板梯队（打板情绪高度）"
          extra={<Tag color="red">最高 {ladder.max_board} 板</Tag>}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              {ladderOption && <ReactECharts option={ladderOption} style={{ height: 220 }} notMerge />}
            </div>
            <Table<LimitUpLeader>
              size="small"
              rowKey="symbol"
              columns={LEADER_COLS}
              dataSource={ladder.leaders}
              pagination={false}
              scroll={{ y: 200 }}
              locale={{ emptyText: "暂无 2 板以上龙头" }}
            />
          </div>
        </Card>
      )}

      <Card
        size="small"
        title="情绪温度历史（每日收盘存档 · 50 为多空分界）"
        className="flex-1"
        classNames={{ body: "flex-1 min-h-0" }}
      >
        {histOption ? (
          <ReactECharts option={histOption} style={{ height: "100%", minHeight: 260 }} notMerge />
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <Empty description="暂无历史（收盘 beat 存档后显示）" />
          </div>
        )}
      </Card>
    </div>
  );
}
