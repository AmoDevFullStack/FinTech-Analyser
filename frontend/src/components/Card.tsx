import type { ReactNode } from "react";

/** The resting surface for a region. Soft radius and a hairline lift (--shadow-1) rather
 * than a heavy border: the card should read as paper on a desk, not as a boxed area.
 */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`flex flex-col gap-4 rounded-2xl border border-rule bg-surface-raised p-6 shadow-1 ${className}`}
    >
      {children}
    </div>
  );
}
