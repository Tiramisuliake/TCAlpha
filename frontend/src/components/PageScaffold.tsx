import type { ReactNode } from "react";

interface PageScaffoldProps {
  children: ReactNode;
  className?: string;
}

export function PageScaffold({ children, className }: PageScaffoldProps) {
  return (
    <div className={`flex-1 flex flex-col gap-4 min-h-0 ${className ?? ""}`}>
      {children}
    </div>
  );
}
