import type { StrategyComparison } from "@/api/types";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { MoneyText } from "@/components/MoneyText";

/** specs/debts.md: the comparison "states the cost difference between avalanche and
 * snowball in rand and in months", and "where the difference is small, the system says
 * so, because a strategy the user abandons is worse than a slightly suboptimal one they
 * finish." Both of those are rendered here rather than left for the reader to work out.
 *
 * The system does not recommend a strategy. It presents costs and lets the user choose,
 * so neither column is marked as the right answer.
 */
export function StrategyComparisonView({ comparison }: { comparison: StrategyComparison }) {
  const rows = [
    { label: "Avalanche — highest rate first", result: comparison.avalanche },
    { label: "Snowball — smallest balance first", result: comparison.snowball },
    ...(comparison.consolidation
      ? [{ label: "Consolidation — one facility", result: comparison.consolidation }]
      : []),
  ];

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-title">Payoff strategies</h2>
        {comparison.difference_is_material ? null : (
          <Chip>Difference is not material</Chip>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead>
            <tr className="bg-surface-sunken text-left text-label text-content-secondary">
              <th className="p-3 font-medium">Strategy</th>
              <th className="p-3 text-right font-medium">Total interest</th>
              <th className="p-3 text-right font-medium">Months to debt free</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {rows.map(({ label, result }) => (
              <tr key={result.strategy}>
                <td className="p-3">{label}</td>
                <td className="p-3 text-right">
                  <MoneyText value={result.total_interest} size="body" />
                </td>
                <td className="p-3 text-right tabular-nums">{result.months_to_free}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-body text-content-secondary">
        Snowball costs{" "}
        <MoneyText
          value={comparison.interest_difference_avalanche_vs_snowball}
          size="body"
        />{" "}
        more in interest than avalanche and takes{" "}
        <span className="tabular-nums">
          {comparison.months_difference_avalanche_vs_snowball}
        </span>{" "}
        months longer.{" "}
        {comparison.difference_is_material
          ? "That difference is material at this debt set."
          : "That difference is small enough that adherence matters more than the ranking."}
      </p>
    </Card>
  );
}
