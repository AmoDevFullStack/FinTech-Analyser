import { Link, useParams } from "react-router-dom";

import { useDebtSchedule, useDebtWhatIf, useDebts } from "@/api/debts";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { WhatIfTable } from "@/features/debts";
import { formatRateAsPercent } from "@/lib/money";

export function DebtDetail() {
  const { debtId = "" } = useParams();
  const { data: debts } = useDebts();
  const { data: schedule, isLoading } = useDebtSchedule(debtId);
  const { data: whatIf } = useDebtWhatIf(debtId);

  const debt = debts?.find((row) => row.id === debtId);

  return (
    <div className="flex flex-col gap-8">
      <Link to="/debts" className="text-label text-accent">
        ← All debts
      </Link>

      {debt ? (
        <Card>
          <h1 className="text-title">{debt.debt_type.replace(/_/g, " ")}</h1>
          <div className="flex flex-wrap gap-8">
            <div className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Balance</span>
              <MoneyText value={debt.current_balance} size="figure-lg" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Rate</span>
              <span className="font-ui text-figure-lg tabular-nums">
                {formatRateAsPercent(debt.annual_rate, { places: 2 })}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Minimum payment</span>
              <MoneyText value={debt.minimum_payment} size="figure-lg" />
            </div>
          </div>
        </Card>
      ) : null}

      {whatIf ? <WhatIfTable rows={whatIf} /> : null}

      <Card>
        <h2 className="text-title">Schedule</h2>
        {isLoading ? (
          <EmptyState message="Loading…" />
        ) : !schedule || schedule.length === 0 ? (
          <EmptyState message="No schedule for this debt." />
        ) : (
          <>
            <p className="text-caption text-content-tertiary">
              {schedule.length} payments. Interest is calculated on the opening balance
              each period and rounded per period, matching how a lender states it.
            </p>
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-body">
                <thead className="sticky top-0 bg-surface-sunken text-left text-label text-content-secondary">
                  <tr>
                    <th className="p-3 font-medium">#</th>
                    <th className="p-3 text-right font-medium">Instalment</th>
                    <th className="p-3 text-right font-medium">Interest</th>
                    <th className="p-3 text-right font-medium">Principal</th>
                    <th className="p-3 text-right font-medium">Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {schedule.map((period) => (
                    <tr key={period.period}>
                      <td className="p-3 tabular-nums">{period.period}</td>
                      <td className="p-3 text-right">
                        <MoneyText value={period.instalment} size="body" />
                      </td>
                      <td className="p-3 text-right">
                        <MoneyText value={period.interest} size="body" />
                      </td>
                      <td className="p-3 text-right">
                        <MoneyText value={period.principal} size="body" />
                      </td>
                      <td className="p-3 text-right">
                        <MoneyText value={period.closing_balance} size="body" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
