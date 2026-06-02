/**
 * PermButton（Phase 7 v0.7.5）：缺权限时按钮 disabled + Tooltip 提示。
 *
 * 用法：
 *   <PermButton perm="strategy.write" type="primary" onClick={...}>新建</PermButton>
 *   <PermButton perm={["sim.order.place"]} hideOnDenied>下单</PermButton>
 *
 * 设计：
 * - super 用户自动绕过（useAuthStore.has 已处理）
 * - 默认 disabled + Tooltip，让 viewer 知道"有这功能但缺权限"
 * - hideOnDenied=true 时彻底隐藏（用于删除等纯破坏性操作）
 * - perm 支持单字符串或字符串数组（数组按"全部都需要"判定）
 *
 * 实现细节：把 AntD ButtonProps 完整透传，自身只在 `disabled` 上叠加。
 */
import { Button, Tooltip } from "antd";
import type { ButtonProps } from "antd";
import { useAuthStore } from "@/store/useAuthStore";

export interface PermButtonProps extends ButtonProps {
  /** 单权限码或多个全部需要的权限码 */
  perm: string | string[];
  /** 缺权限时彻底隐藏（默认 false：仅 disabled + tooltip） */
  hideOnDenied?: boolean;
  /** 自定义 tooltip 文案；默认 "需要权限：xxx" */
  deniedTip?: string;
}

export function PermButton({
  perm,
  hideOnDenied = false,
  deniedTip,
  disabled,
  children,
  ...rest
}: PermButtonProps) {
  const has = useAuthStore((s) => s.has);
  const perms = Array.isArray(perm) ? perm : [perm];
  const ok = perms.every((p) => has(p));

  if (!ok && hideOnDenied) return null;

  const tip = !ok ? deniedTip ?? `需要权限：${perms.join(", ")}` : undefined;
  const finalDisabled = disabled || !ok;

  const button = (
    <Button {...rest} disabled={finalDisabled}>
      {children}
    </Button>
  );
  return tip ? <Tooltip title={tip}>{button}</Tooltip> : button;
}
