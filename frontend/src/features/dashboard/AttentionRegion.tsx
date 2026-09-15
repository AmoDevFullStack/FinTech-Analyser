import type { Position } from "@/api/types";

/** Region 5 — active risk flags. Per specs/dashboard.md, this region is ABSENT (not a
 * green all-clear) when there are none, so it never trains the user to skim past it.
 * Always absent in this "Now" slice since risk detection is Next-phase per PLAN.md.
 */
export function AttentionRegion({ position }: { position: Position }) {
  if (position.active_risk_flags === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-signal-critical bg-surface-raised p-6">
      <h2 className="text-title">Attention</h2>
      <p className="text-body text-signal-critical">
        {position.active_risk_flags} active risk flag(s).
      </p>
    </div>
  );
}
