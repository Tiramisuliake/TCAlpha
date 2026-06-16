import { useState } from "react";
import { Alert, Button, Card, Col, Empty, Input, InputNumber, Row, Statistic, Table } from "antd";
import { LineChartOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import type { ColumnsType } from "antd/es/table";
import { runLimitUpPremium } from "@/api/screener";
import type { BoardGroupStat } from "@/types";

function pct(v: number | undefined | null): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(2)}%`;
}

/**
 * 打板复盘：涨停次日溢价统计。扫历史涨停日，统计次日开盘/收盘/最高溢价 +
 * 红盘率，并按连板高度（1板/2板/3板+）分组，验证打板策略的次日期望与胜率。
 * symbol 留空 = 全市场（已下载历史的票）汇总。
 */
export default function LimitUpStats() {
  const [symbol, setSymbol] = useState("");
  const [lookback, setLookback] = useState(250);

  const mut = useMutation({
    mutationFn: () => runLimitUpPremium({ symbol: symbol.trim() || undefined, lookback }),
  });
  const res = mut.data;

  const cols: ColumnsType<BoardGroupStat> = [
    { title: "连板", dataIndex: "boards", width: 100 },
    { title: "样本数", dataIndex: "count", align: "right" },
    {
      title: "次日均开盘溢价",
      dataIndex: "avg_open",
      align: "right",
      render: (v: number) => <span className={`num ${v >= 0 ? "up" : "down"}`}>{pct(v)}</span>,
    },
    {
      title: "次日均收盘溢价",
      dataIndex: "avg_close",
      align: "right",
      render: (v: number) => <span className={`num ${v >= 0 ? "up" : "down"}`}>{pct(v)}</span>,
    },
    {
      title: "次日红盘率",
      dataIndex: "win_rate",
      align: "right",
      render: (v: number) => <span className="num">{pct(v)}</span>,
    },
    {
      title: "晋级率（次日续板）",
      dataIndex: "promote_rate",
      align: "right",
      render: (v: number) => <span className="num font-medium text-orange-500">{pct(v)}</span>,
    },
  ];

  return (
    <>
      <Card size="small" title="打板复盘（涨停次日溢价统计）">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-slate-400">标的（留空=全市场）</span>
            <Input
              size="small"
              placeholder="sh600000 或留空"
              style={{ width: 180 }}
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              allowClear
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-slate-400">回看交易日</span>
            <InputNumber size="small" min={20} max={1200} value={lookback} onChange={(v) => setLookback(v ?? 250)} />
          </div>
          <Button type="primary" icon={<LineChartOutlined />} loading={mut.isPending} onClick={() => mut.mutate()}>
            统计
          </Button>
        </div>
        <div className="mt-2 text-xs text-slate-400">
          统计历史涨停日的「次日」表现，溢价以涨停日收盘价为基准，按连板高度分组 —— 验证打板的次日期望、胜率与晋级率（N 板次日续板成 N+1 的概率）
        </div>
      </Card>

      {res && !res.ready && (
        <Alert type="info" showIcon message="尚无历史 K 线数据，请先到「数据」页下载日 K 后再统计" />
      )}

      {res?.ready && res.count === 0 && (
        <Alert type="warning" showIcon message="回看区间内未发现涨停日（可放大回看天数或换标的）" />
      )}

      {res?.ready && res.count > 0 && (
        <>
          <Card size="small" title={`总体（样本 ${res.count} 个涨停日）`}>
            <Row gutter={[8, 8]}>
              <Col span={6}>
                <Statistic title="次日均开盘溢价" value={pct(res.avg_open_premium)} valueStyle={{ fontSize: 18, color: res.avg_open_premium >= 0 ? "#ef4444" : "#10b981" }} />
              </Col>
              <Col span={6}>
                <Statistic title="次日均收盘溢价" value={pct(res.avg_close_premium)} valueStyle={{ fontSize: 18, color: res.avg_close_premium >= 0 ? "#ef4444" : "#10b981" }} />
              </Col>
              <Col span={6}>
                <Statistic title="次日均最高溢价" value={pct(res.avg_high_premium)} valueStyle={{ fontSize: 18, color: "#ef4444" }} />
              </Col>
              <Col span={6}>
                <Statistic title="次日红盘率" value={pct(res.next_day_win_rate)} valueStyle={{ fontSize: 18 }} />
              </Col>
            </Row>
          </Card>

          <Card size="small" title="按连板高度分组" className="flex-1" classNames={{ body: "flex-1 flex flex-col min-h-0" }}>
            <Table<BoardGroupStat>
              rowKey="boards"
              size="small"
              dataSource={res.by_boards}
              columns={cols}
              pagination={false}
            />
          </Card>
        </>
      )}

      {!res && (
        <Card className="flex-1" classNames={{ body: "flex-1 flex items-center justify-center" }}>
          <Empty description="输入标的或留空（全市场）后点「统计」" />
        </Card>
      )}
    </>
  );
}
