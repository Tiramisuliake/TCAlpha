import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Result } from "antd";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * 全局错误边界：捕获子树渲染期异常，避免单页崩溃白屏整站。
 * React 19 仍需 class 组件实现（无 Hook 等价 API）—— CLAUDE 允许的例外。
 *
 * 用法：在 App 的 <Outlet/> 外层包一层，并以 key={location.pathname}
 * 让切换路由时自动重置错误态。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  private handleReset = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <Result
            status="error"
            title="页面出错了"
            subTitle={error.message || "渲染时发生异常，可重试或刷新页面"}
            extra={[
              <Button type="primary" key="retry" onClick={this.handleReset}>
                重试
              </Button>,
              <Button key="reload" onClick={() => location.reload()}>
                刷新页面
              </Button>,
            ]}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
