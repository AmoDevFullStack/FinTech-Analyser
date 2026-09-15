import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { asMoney } from "@/lib/money";
import { formatDate } from "@/lib/dates";
import type { Position } from "@/api/types";

/** Region 3 — what is coming in the next 30 days. See specs/dashboard.md.
 *
 * Always empty in this "Now" slice: obligation tracking depends on the Debt/Expense
 * entities PLAN.md defers to Next. Rendering the documented empty state rather than
 * fabricating a due date is the honest choice here.
 */
export function UpcomingRegion({ position }: { position: Position }) {
  return (
    <Card>
      <h2 className="text-title">What is coming</h2>
      {position.upcoming_obligations.length === 0 ? (
        <EmptyState message="No obligations tracked yet." />
      ) : (
        <ul className="flex flex-col divide-y divide-rule">
          {position.upcoming_obligations.map((obligation) => (
            <li
              key={`${obligation.label}-${obligation.due_on}`}
              className="flex items-baseline justify-between gap-4 py-3"
            >
              <div className="flex flex-col gap-0.5">
                <span className="text-body">{obligation.label}</span>
                <span className="text-caption text-content-tertiary">
                  {formatDate(obligation.due_on)}
                </span>
              </div>
              <MoneyText value={asMoney(obligation.amount)} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
