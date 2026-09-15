import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`flex flex-col gap-4 rounded-lg border border-rule bg-surface-raised p-6 ${className}`}
    >
      {children}
    </div>
  );
}
