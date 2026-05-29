import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { FeedbackBridge } from "@/components/FeedbackBridge";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

const tcAlphaTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#1677ff",
    borderRadius: 8,
    controlHeight: 36,
    colorBgLayout: "#f6f8fb",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: {
      headerBg: "transparent",
      headerHeight: 60,
      headerPadding: "0 24px",
      siderBg: "#0f172a",
      bodyBg: "#f6f8fb",
    },
    Menu: {
      itemHeight: 44,
      itemBorderRadius: 8,
      itemMarginInline: 8,
      itemPaddingInline: 14,
      itemSelectedBg: "#e6f4ff",
      itemSelectedColor: "#1677ff",
      itemHoverBg: "#f1f5f9",
      iconSize: 16,
      darkItemBg: "transparent",
      darkSubMenuItemBg: "transparent",
      darkItemColor: "#cbd5e1",
      darkItemHoverBg: "#1e293b",
      darkItemHoverColor: "#f8fafc",
      darkItemSelectedBg: "rgba(59, 130, 246, 0.18)",
      darkItemSelectedColor: "#60a5fa",
      darkPopupBg: "#0f172a",
    },
    Card: {
      headerHeight: 52,
      headerFontSize: 15,
      headerBg: "transparent",
      borderRadiusLG: 10,
      boxShadowTertiary: "0 1px 2px 0 rgba(15, 23, 42, 0.04)",
    },
    Table: {
      headerBg: "#f8fafc",
      headerColor: "#64748b",
      headerSplitColor: "#e2e8f0",
      borderColor: "#e2e8f0",
      rowHoverBg: "#f8fafc",
      cellPaddingBlock: 12,
    },
    Button: {
      controlHeight: 36,
      borderRadius: 8,
    },
    Input: {
      controlHeight: 36,
    },
    Select: {
      controlHeight: 36,
    },
    InputNumber: {
      controlHeight: 36,
    },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={tcAlphaTheme}>
      <AntApp>
        <FeedbackBridge />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
