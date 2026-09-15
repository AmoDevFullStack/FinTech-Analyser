import { formatDateTime } from "@/lib/dates";
import { formatMoney, type Money } from "@/lib/money";
import type { Projected } from "@/api/types";

/** Renders a Projected<Money> together with its provenance — see docs/frontend.md §6 and
 * docs/design-system.md §1: "make the certainty of a figure legible before the figure is
 * read." There is deliberately no prop that accepts a bare value: the type only accepts
 * the wrapper, so a component cannot render a projection without also rendering its date.
 */
export function ProjectedValue({ projected }: { projected: Projected<Money> }) {
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="border-b border-rule-meaning pb-0.5 font-ui text-figure tabular-nums">
        {formatMoney(projected.value)}
      </span>
      <span className="text-caption text-content-tertiary">
        {projected.isStale ? "Stale — " : "Projected "}
        {formatDateTime(projected.generatedAt)}
      </span>
    </span>
  );
}
