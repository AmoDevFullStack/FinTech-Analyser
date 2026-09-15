import type { WhatIfRow } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";

/** specs/debts.md's what-if: "The marginal effect of an additional R100, R500, or R1,000
 * per month: months saved and interest saved." Every figure here is computed by
 * app/domain/debt_payoff.py against this debt's own baseline schedule.
 */
export function WhatIfTable({ rows }: { rows: WhatIfRow[] }) {
  if (rows.length === 0) {
    return (
      <Card>
        <EmptyState message="No what-if figures for this debt." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">Paying more each month</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead>
            <tr className="bg-surface-sunken text-left text-label text-content-secondary">
              <th className="p-3 font-medium">Extra per month</th>
              <th className="p-3 text-right font-medium">Months saved</th>
              <th className="p-3 text-right font-medium">Interest saved</th>
              <th className="p-3 text-right font-medium">Months to clear</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {rows.map((row) => (
              <tr key={row.extra_monthly}>
                <td className="p-3">
                  <MoneyText value={row.extra_monthly} size="body" />
                </td>
                <td className="p-3 text-right tabular-nums">{row.months_saved}</td>
                <td className="p-3 text-right">
                  <MoneyText value={row.interest_saved} size="body" />
                </td>
                <td className="p-3 text-right tabular-nums">{row.months_to_free}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
