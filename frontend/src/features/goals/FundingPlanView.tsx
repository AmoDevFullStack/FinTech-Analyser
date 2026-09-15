import { useFundingPlan, useGoals } from "@/api/goals";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";

/** specs/goals.md's competition section: "Goals are not modelled in isolation because
 * they are not funded in isolation." This shows the funding order and what slips, rather
 * than each goal appearing independently achievable.
 */
export function FundingPlanView() {
  const { data: plan, isLoading } = useFundingPlan();
  const { data: goals } = useGoals();

  if (isLoading) return <Card><EmptyState message="Loading…" /></Card>;
  if (!plan || plan.fundings.length === 0) {
    return (
      <Card>
        <EmptyState message="No goals to fund yet." />
      </Card>
    );
  }

  const nameFor = (goalId: string) =>
    goals?.find((goal) => goal.id === goalId)?.name ?? "Goal";

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-title">Funding order</h2>
        {plan.is_over_committed ? <Chip>More required than available</Chip> : null}
      </div>

      <p className="text-body text-content-secondary">
        Goals need <MoneyText value={plan.total_required} size="body" /> a month in total
        against <MoneyText value={plan.available_cash_flow} size="body" /> of available
        cash flow. Funding runs in priority order.
      </p>

      <ol className="flex flex-col divide-y divide-rule">
        {plan.fundings.map((funding) => (
          <li key={funding.goal_id} className="flex items-baseline justify-between gap-4 py-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-body">
                {funding.priority}. {nameFor(funding.goal_id)}
              </span>
              <span className="text-caption text-content-tertiary">
                {funding.is_fully_funded
                  ? "Fully funded"
                  : funding.slippage_months === null
                    ? "Not funded at all at current cash flow"
                    : `${funding.slippage_months} months later than the target date`}
              </span>
            </div>
            <div className="text-right">
              <MoneyText value={funding.funded_monthly} size="body" />
              <span className="block text-caption text-content-tertiary">
                of <MoneyText value={funding.required_monthly} size="body" /> needed
              </span>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
