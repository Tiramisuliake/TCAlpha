import type { ReactNode } from "react";
import { Button, Result, Spin } from "antd";
import { useNavigate } from "react-router";
import { useAuthStore } from "@/store/useAuthStore";

interface RequirePermProps {
  /** 需要的权限码（super 自动放行，由 useAuthStore.has 处理） */
  perm: string;
  children: ReactNode;
}

/**
 * 路由级权限守卫：无权限直接渲染 403，避免进页面后多个 API 各自 401/403
 * 弹错轰炸。me 尚未加载时显示 Spin，防止登录刚跳转时误判 403 闪现。
 */
export function RequirePerm({ perm, children }: RequirePermProps) {
  const me = useAuthStore((s) => s.me);
  const has = useAuthStore((s) => s.has);
  const navigate = useNavigate();

  if (!me) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (!has(perm)) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Result
          status="403"
          title="403"
          subTitle={`无访问权限，需要：${perm}`}
          extra={
            <Button type="primary" onClick={() => navigate("/")}>
              返回首页
            </Button>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
