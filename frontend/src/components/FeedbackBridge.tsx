/**
 * 把 AntD App.useApp() 拿到的 hook 版 message / notification 注入全局 feedback holder。
 * 必须放在 <App> 组件内部，且只渲染一次。
 */
import { App } from "antd";
import { useEffect } from "react";
import { setFeedbackApis } from "@/utils/feedback";

export function FeedbackBridge() {
  const { message, notification } = App.useApp();
  useEffect(() => {
    setFeedbackApis({ message, notification });
  }, [message, notification]);
  return null;
}
