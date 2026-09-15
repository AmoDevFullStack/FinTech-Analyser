import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { asMoney } from "@/lib/money";
import type { Position } from "@/api/types";

/** Region 2 — this month's cash flow, rendered as a flow, not a pie chart, per
 * specs/dashboard.md.
 */
export function CashFlowRegion({ position }: { position: Position }) {
  if (position.monthly_income === null) {
    return (
      <Card>
        <h2 className="text-title">This month&apos;s cash flow</h2>
        <EmptyState message="No transaction history yet." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">This month&apos;s cash flow</h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Income</span>
          <MoneyText value={asMoney(position.monthly_income)} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Essential</span>
          <MoneyText value={asMoney(position.monthly_essential!)} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Discretionary</span>
          <MoneyText value={asMoney(position.monthly_discretionary!)} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Remaining</span>
          <MoneyText value={asMoney(position.projected_cash_flow!)} />
        </div>
      </div>
    </Card>
  );
}
