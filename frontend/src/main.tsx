import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { FeedbackBridge } from "@/components/FeedbackBridge";
import { feedback } from "@/utils/feedback";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/index.css";

function extractErrMsg(err: unknown): string {
  const e = err as {
    response?: { status?: number; data?: { detail?: string } };
    message?: string;
  };
  return e?.response?.data?.detail ?? e?.message ?? "请求失败";
}

function isAuthErr(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 401;
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
  // 读：仅首次加载失败提示；后台 refetch 失败（已有缓存）静默，避免 toast 轰炸
  queryCache: new QueryCache({
    onError: (err, query) => {
      if (isAuthErr(err)) return; // 401 由 client 拦截器统一处理（refresh / 跳转）
      if (query.state.data === undefined) feedback.error(extractErrMsg(err));
    },
  }),
  // 写：用户主动操作，失败必须反馈
  mutationCache: new MutationCache({
    onError: (err) => {
      if (isAuthErr(err)) return;
      feedback.error(extractErrMsg(err));
    },
  }),
});

/**
 * TCAlpha Industrial Theme（v0.7.x）
 *
 * 美学方向：Industrial / Utilitarian（Bloomberg 日间模式 / IB TWS 风）
 * 差异化锚点：Mono Numeric — 所有数字 / 代码 / ID / 时间走 IBM Plex Mono +
 *   tabular-nums，强化"仪表盘等宽对齐"感
 *
 * Tokens：
 * - 主色：#1a4fff（强蓝，比 antd 默认 #1677ff 更工业）
 * - accent：#FFB800（纯黄，警示 / 选中点缀）
 * - 圆角：2px（几乎不圆，maintain 工业感）
 * - 字体：IBM Plex Sans / Mono（fallback 到系统）
 * - shadow：全去（用 hairline border 替代）
 */
const SANS = "'IBM Plex Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif";

const tcAlphaTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#1a4fff",
    colorInfo: "#1a4fff",
    colorSuccess: "#00a778",
    colorWarning: "#FFB800",
    colorError: "#ef4444",

    borderRadius: 2,
    borderRadiusLG: 4,
    borderRadiusSM: 2,
    borderRadiusXS: 2,

    controlHeight: 32,
    colorBgLayout: "#eef0f5",
    colorBgContainer: "#ffffff",
    colorBorder: "#d8dce4",
    colorBorderSecondary: "#e5e7eb",

    fontFamily: SANS,
    fontSize: 13,

    // 全平面化：移除阴影
    boxShadow: "none",
    boxShadowSecondary: "none",
    boxShadowTertiary: "none",

    wireframe: false,
  },
  components: {
    Layout: {
      headerBg: "transparent",
      headerHeight: 56,
      headerPadding: "0 20px",
      siderBg: "#0e1116",
      bodyBg: "#eef0f5",
    },
    Menu: {
      itemHeight: 40,
      itemBorderRadius: 2,
      itemMarginInline: 6,
      itemPaddingInline: 12,
      itemSelectedBg: "rgba(255, 184, 0, 0.12)",
      itemSelectedColor: "#FFB800",
      itemHoverBg: "#1e293b",
      iconSize: 14,
      darkItemBg: "transparent",
      darkSubMenuItemBg: "transparent",
      darkItemColor: "#9ca8b8",
      darkItemHoverBg: "#1c2229",
      darkItemHoverColor: "#f5f7fa",
      darkItemSelectedBg: "rgba(255, 184, 0, 0.16)",
      darkItemSelectedColor: "#FFB800",
      darkPopupBg: "#0e1116",
    },
    Card: {
      headerHeight: 40,
      headerHeightSM: 32,
      headerFontSize: 13,
      headerFontSizeSM: 12,
      headerBg: "#fafbfc",
      borderRadiusLG: 2,
      boxShadowTertiary: "none",
      colorBorderSecondary: "#d8dce4",
      paddingLG: 16,
    },
    Table: {
      headerBg: "#fafbfc",
      headerColor: "#5a6472",
      headerSplitColor: "#d8dce4",
      borderColor: "#e5e7eb",
      rowHoverBg: "#f7f9fc",
      cellPaddingBlock: 8,
      cellPaddingInline: 10,
      cellFontSizeSM: 12,
      borderRadius: 2,
    },
    Button: {
      controlHeight: 32,
      borderRadius: 2,
      fontWeight: 500,
      primaryShadow: "none",
      dangerShadow: "none",
      defaultShadow: "none",
    },
    Input: { controlHeight: 32, borderRadius: 2, activeShadow: "none" },
    InputNumber: { controlHeight: 32, borderRadius: 2 },
    Select: { controlHeight: 32, borderRadius: 2 },
    DatePicker: { controlHeight: 32, borderRadius: 2 },
    Tag: { borderRadiusSM: 2, defaultBg: "#eef0f5", defaultColor: "#0f172a" },
    Statistic: { titleFontSize: 12, contentFontSize: 20 },
    Drawer: { paddingLG: 20 },
    Modal: { borderRadiusLG: 2 },
    Segmented: { borderRadius: 2, controlPaddingHorizontal: 12 },
    Tooltip: { borderRadius: 2 },
    Tabs: { itemSelectedColor: "#1a4fff", inkBarColor: "#1a4fff" },
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
