import { useDismissRecommendation, useRecommendations } from "@/api/recommendations";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";

const RULE_LABELS: Record<string, string> = {
  redirect_to_highest_rate_debt: "Surplus against the highest-rate debt",
  build_emergency_cover: "Emergency cover",
  subscription_audit: "Recurring subscription",
  utilisation_reduction: "Credit utilisation",
  goal_contribution_shortfall: "Goal contribution gap",
  refinance_candidate: "Rate above your own average",
  surplus_not_allocated: "Unallocated surplus",
};

const BENEFIT_LABELS: Record<string, string> = {
  interest_saved: "Interest saved",
  cover_gap: "Gap to three months",
  annual_cost: "Annual cost",
  repayment_amount: "Repayment needed",
  monthly_gap: "Monthly gap",
  annual_interest_difference: "Interest difference, first year",
  annual_amount_if_saved: "Value over a year",
};

/** Every line here was produced by a rule over computed figures, never by a model, and
 * every one carries the computation that justifies it (specs/recommendations.md). The
 * text is a calculation, not an instruction — the server composes it that way and it is
 * rendered verbatim.
 */
export function RecommendationList() {
  const { data: recommendations, isLoading } = useRecommendations();
  const dismiss = useDismissRecommendation();

  if (isLoading) {
    return (
      <Card>
        <EmptyState message="Loading…" />
      </Card>
    );
  }

  if (!recommendations || recommendations.length === 0) {
    return (
      <Card>
        <h2 className="text-title">Worth knowing</h2>
        <EmptyState message="Nothing to surface right now. This list is capped at five and only carries items the system can quantify." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">Worth knowing</h2>
      <ul className="flex flex-col divide-y divide-rule">
        {recommendations.map((recommendation) => (
          <li key={recommendation.id} className="flex flex-col gap-3 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <span className="text-body font-medium">
                {RULE_LABELS[recommendation.rule_id] ?? recommendation.rule_id}
              </span>
              <span className="flex flex-col items-end">
                <MoneyText value={recommendation.benefit_amount} size="figure" />
                <span className="text-caption text-content-tertiary">
                  {BENEFIT_LABELS[recommendation.benefit_kind] ?? recommendation.benefit_kind}
                </span>
              </span>
            </div>

            <p className="text-body text-content-secondary">{recommendation.explanation}</p>

            <span className="text-caption text-content-tertiary">
              Computed {formatDate(recommendation.generated_on)} · from{" "}
              {recommendation.computation_reference}
            </span>

            <div>
              <Button
                onClick={() => dismiss.mutate(recommendation.id)}
                disabled={dismiss.isPending}
              >
                Dismiss for 60 days
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
