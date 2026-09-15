import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Outlined, shape-carried badge — docs/design-system.md §5's "Stale chip — outlined,
 * with a shape, not a colour fill" applied wherever a status needs a label that isn't a
 * figure. Never colour-only: the icon and text both carry the meaning.
 */
export function Chip({ icon: Icon, children }: { icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-rule-meaning px-2 py-0.5 text-caption text-content-secondary">
      {Icon ? <Icon size={12} strokeWidth={2} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
