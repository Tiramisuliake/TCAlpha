import { useState } from "react";
import { Card, Space, Tabs, Tag } from "antd";
import { RobotOutlined } from "@ant-design/icons";
import { PageScaffold } from "@/components/PageScaffold";
import Chat from "./Chat";
import Watchlist from "./Watchlist";
import AlertList from "./AlertList";

type TabKey = "chat" | "alerts" | "watchlist";

export default function AI() {
  const [tab, setTab] = useState<TabKey>("chat");

  return (
    <PageScaffold>
      <Card
        title={
          <Space>
            <RobotOutlined />
            <span>AI</span>
            <Tag color="blue">DeepSeek</Tag>
          </Space>
        }
        className="flex-1"
        classNames={{ body: "flex-1 flex flex-col min-h-0 !p-3" }}
      >
        <Tabs
          activeKey={tab}
          onChange={(k) => setTab(k as TabKey)}
          className="!flex-1 !flex !flex-col [&_.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:flex [&_.ant-tabs-tabpane]:flex-col"
          items={[
            { key: "chat", label: "助手聊天", children: <Chat /> },
            {
              key: "alerts",
              label: "AI 盯盘",
              children: <AlertList />,
            },
            {
              key: "watchlist",
              label: "关注列表",
              children: <Watchlist onJumpAlerts={() => setTab("alerts")} />,
            },
          ]}
        />
      </Card>
    </PageScaffold>
  );
}
