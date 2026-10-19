import type { Debt } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";

import { DebtRow } from "./DebtRow";

export function DebtList({ debts }: { debts: Debt[] }) {
  if (debts.length === 0) {
    return (
      <Card>
        <EmptyState message="No debts recorded yet. Adding one lets the system schedule it, compare payoff strategies, and include its repayments in every projection." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">Debts</h2>
      <p className="text-caption text-content-tertiary">
        Select a debt to change its balance, rate, or payment. The arrow opens its full
        schedule.
      </p>
      <ul className="flex flex-col divide-y divide-rule">
        {debts.map((debt) => (
          <DebtRow key={debt.id} debt={debt} />
        ))}
      </ul>
    </Card>
  );
}
