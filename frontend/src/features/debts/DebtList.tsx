import { Link } from "react-router-dom";

import type { Debt } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { formatRateAsPercent } from "@/lib/money";

const DEBT_TYPE_LABELS: Record<Debt["debt_type"], string> = {
  credit_card: "Credit card",
  personal_loan: "Personal loan",
  vehicle: "Vehicle finance",
  home_loan: "Home loan",
  store_account: "Store account",
  other: "Other",
};

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
      <ul className="flex flex-col divide-y divide-rule">
        {debts.map((debt) => (
          <li key={debt.id} className="flex items-baseline justify-between gap-4 py-3">
            <div className="flex flex-col gap-0.5">
              <Link to={`/debts/${debt.id}`} className="text-body text-accent">
                {DEBT_TYPE_LABELS[debt.debt_type]}
              </Link>
              <span className="text-caption text-content-tertiary">
                {formatRateAsPercent(debt.annual_rate, { places: 2 })} · minimum{" "}
                <MoneyText value={debt.minimum_payment} size="body" /> · since{" "}
                {formatDate(debt.started_on)}
              </span>
            </div>
            <MoneyText value={debt.current_balance} />
          </li>
        ))}
      </ul>
    </Card>
  );
}
