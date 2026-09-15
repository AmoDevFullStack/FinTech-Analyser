import { AlertTriangle } from "lucide-react";

import { useGoalProgress } from "@/api/goals";
import type { Goal } from "@/api/types";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";

const PROGRESS_SOURCE_LABELS: Record<string, string> = {
  linked_account: "Progress from the linked account balance",
  contributions: "Progress from recorded contributions",
  none: "No progress recorded yet",
};

/** specs/goals.md: "Indefinite progress bars on unachievable goals are a way of avoiding
 * telling the user something true." So an unachievable goal states the monthly shortfall
 * and how far the date slips, and the required-versus-observed gap is always visible —
 * the spec calls that gap the most useful thing this feature produces.
 */
export function GoalProgressCard({ goal }: { goal: Goal }) {
  const { data: progress, isLoading, isError } = useGoalProgress(goal.id);

  if (isLoading) return <Card><EmptyState message="Loading…" /></Card>;
  if (isError || !progress) {
    return (
      <Card>
        <EmptyState message="Could not load this goal's progress." />
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-title">{goal.name}</h2>
        {progress.is_achievable ? null : (
          <Chip icon={AlertTriangle}>Not achievable at current cash flow</Chip>
        )}
      </div>

      <div className="flex flex-wrap gap-8">
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Held</span>
          <MoneyText value={progress.current_amount} size="figure-lg" />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Target</span>
          <MoneyText value={progress.target_amount} size="figure-lg" />
          <span className="text-caption text-content-tertiary">
            by {formatDate(goal.target_date)}
          </span>
        </div>
      </div>

      <dl className="flex flex-col gap-2 text-body">
        <div className="flex justify-between gap-4">
          <dt className="text-content-secondary">Needed each month</dt>
          <dd>
            <MoneyText value={progress.required_monthly_contribution} size="body" />
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-content-secondary">Actually going in each month</dt>
          <dd>
            <MoneyText value={progress.observed_monthly_rate} size="body" />
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-content-secondary">On current behaviour, reached</dt>
          <dd>
            {progress.projected_achievement_date
              ? formatDate(progress.projected_achievement_date)
              : "Not reached at the current rate"}
          </dd>
        </div>
      </dl>

      {progress.is_achievable ? null : (
        <p className="text-body text-signal-critical">
          Short by <MoneyText value={progress.monthly_shortfall} size="body" /> a month
          against available cash flow
          {progress.date_slippage_months === null
            ? "."
            : `, and ${progress.date_slippage_months} months behind the target date.`}
        </p>
      )}

      <p className="text-caption text-content-tertiary">
        {PROGRESS_SOURCE_LABELS[progress.progress_source]}
      </p>
    </Card>
  );
}
