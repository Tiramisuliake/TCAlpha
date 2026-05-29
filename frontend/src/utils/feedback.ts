/**
 * 全局反馈 API holder（Phase 7 v0.7.1 hotfix）。
 *
 * 背景：AntD v5 静态 `message.xxx()` 不读 ConfigProvider 上下文，
 * 在 React 19 严格模式 + 无 <App> 包裹时 toast 会被静默吞掉。
 *
 * 用法：
 * - 组件里：用 `App.useApp()` 拿 hook 版本 message
 * - 非组件（axios 拦截器、Zustand store、Promise tap）：用本模块的 `feedback.error(...)`
 *
 * 注入：main.tsx 渲染 <FeedbackBridge /> 调 `setFeedbackApis` 一次性挂上。
 */
import type { MessageInstance } from "antd/es/message/interface";
import type { NotificationInstance } from "antd/es/notification/interface";

let messageApi: MessageInstance | null = null;
let notificationApi: NotificationInstance | null = null;

export function setFeedbackApis(opts: {
  message: MessageInstance;
  notification: NotificationInstance;
}) {
  messageApi = opts.message;
  notificationApi = opts.notification;
}

/** Promise-style feedback 适配器：bridge 未注入时降级到 console，保证调试可见。 */
export const feedback = {
  success(msg: string) {
    messageApi ? messageApi.success(msg) : console.info("[feedback]", msg);
  },
  error(msg: string) {
    messageApi ? messageApi.error(msg) : console.error("[feedback]", msg);
  },
  info(msg: string) {
    messageApi ? messageApi.info(msg) : console.info("[feedback]", msg);
  },
  warning(msg: string) {
    messageApi ? messageApi.warning(msg) : console.warn("[feedback]", msg);
  },
  notify(title: string, description?: string) {
    if (notificationApi) {
      notificationApi.info({ message: title, description });
    } else {
      console.info("[notify]", title, description);
    }
  },
};
