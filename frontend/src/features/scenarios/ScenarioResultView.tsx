import type { ReactNode } from "react";

import { Card } from "@/components/Card";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { asMoney, asRate, formatRateAsPercent } from "@/lib/money";
import type { ScenarioResult } from "@/api/types";

/** Renders impact summary and both period series from one response — see
 * specs/scenarios.md: "before-and-after renders from one response."
 */
export function ScenarioResultView({ result }: { result: ScenarioResult }) {
  const { impact } = result;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Metric label="Monthly cash-flow impact" value={<MoneyText value={asMoney(impact.monthly_cash_flow_delta)} />} />
        <Metric label="Disposable income after" value={<MoneyText value={asMoney(impact.disposable_income_after)} />} />
        <Metric
          label="Debt-to-income"
          value={
            <span className="text-figure tabular-nums">
              {formatRateAsPercent(asRate(impact.debt_to_income_before))} →{" "}
              {formatRateAsPercent(asRate(impact.debt_to_income_after))}
            </span>
          }
        />
        <Metric label="Emergency fund after" value={<span className="text-figure">{impact.emergency_fund_months_after} months</span>} />
        <Metric label="Net worth at 60 months" value={<MoneyText value={asMoney(impact.net_worth_at_60_months)} />} />
        <Metric
          label="New debt paid off"
          value={<span className="text-figure">{impact.debt_free_date ? formatDate(impact.debt_free_date) : "—"}</span>}
        />
      </div>

      <Card>
        <h3 className="text-title">Net worth: scenario vs. baseline</h3>
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-rule text-left text-label text-content-secondary">
              <th className="px-3 py-2">Month</th>
              <th className="px-3 py-2 text-right">Baseline net worth</th>
              <th className="px-3 py-2 text-right">Scenario net worth</th>
            </tr>
          </thead>
          <tbody>
            {result.periods.map((period, index) => (
              <tr key={period.month} className="border-b border-rule">
                <td className="px-3 py-2 text-caption text-content-tertiary">{period.month}</td>
                <td className="px-3 py-2 text-right">
                  <MoneyText value={asMoney(result.baseline_periods[index].net_worth)} size="body" />
                </td>
                <td className="px-3 py-2 text-right">
                  <MoneyText value={asMoney(period.net_worth)} size="body" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card>
      <span className="text-label text-content-secondary">{label}</span>
      {value}
    </Card>
  );
}
