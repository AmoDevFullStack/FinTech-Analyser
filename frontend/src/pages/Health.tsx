import { Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useHealthAssessment, useHealthMonths, useRefreshHealthAssessment } from "@/api/health";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { HealthBreakdown } from "@/features/dashboard";

const MONTH_NAMES: Record<string, string> = {
  "01": "January",
  "02": "February",
  "03": "March",
  "04": "April",
  "05": "May",
  "06": "June",
  "07": "July",
  "08": "August",
  "09": "September",
  "10": "October",
  "11": "November",
  "12": "December",
};

function monthLabel(month: string): string {
  const [year, index] = month.split("-");
  const name = MONTH_NAMES[index];
  return name ? `${name} ${year}` : month;
}

export function Health() {
  // Undefined means "the most recent month", which is what the page opens on. A month the
  // reader picks replaces it, and picking is what makes the score a series rather than a
  // single verdict about now.
  const [month, setMonth] = useState<string | undefined>();

  const { data: assessment, isLoading, error } = useHealthAssessment(month);
  const months = useHealthMonths();
  const refresh = useRefreshHealthAssessment();

  const notYetAssessed = error instanceof ApiError && error.status === 404;
  const series = months.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-title">Financial health</h1>
        <div className="flex items-center gap-4">
          {series.length > 0 ? (
            <label className="flex items-center gap-2 text-caption text-content-secondary">
              <span>Month</span>
              <select
                className="rounded-lg border border-rule bg-surface-raised px-3 py-2 text-body"
                value={month ?? assessment?.month ?? ""}
                onChange={(event) => setMonth(event.target.value)}
              >
                {[...series].reverse().map((entry) => (
                  <option key={entry.month} value={entry.month}>
                    {monthLabel(entry.month)} · {entry.score}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <Link to="/" className="text-label text-accent">
            Back to dashboard
          </Link>
        </div>
      </div>

      {isLoading ? (
        <EmptyState message="Loading…" />
      ) : notYetAssessed ? (
        <div className="flex flex-col gap-4">
          <EmptyState
            message={
              month
                ? `${monthLabel(month)} has not been assessed.`
                : "Not yet assessed."
            }
          />
          <Button
            variant="primary"
            icon={Play}
            className="w-fit"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? "Working it out…" : "Assess my months"}
          </Button>
        </div>
      ) : assessment ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <p className="text-body text-content-secondary">
              {monthLabel(assessment.month)}
              {assessment.historical_basis ? (
                <span className="text-caption text-content-tertiary">
                  {" "}
                  — worked out from that month's income, spending and closing balance. Your
                  debt repayments and card limits are counted as they stand today, because
                  what they were then is not recorded.
                </span>
              ) : null}
            </p>
            {/* How much of the score is standing on actual statement lines. A month scored
                from 140 transactions and one scored from four are not the same claim, and
                the score alone cannot show the difference. */}
            {assessment.evidence ? (
              <p className="text-caption text-content-tertiary">
                {assessment.evidence.transactions_in_month} transactions in this month ·{" "}
                {assessment.evidence.months_of_history}{" "}
                {assessment.evidence.months_of_history === 1 ? "month" : "months"} of history
                {assessment.evidence.transactions_in_month === 0
                  ? " · nothing recorded for this month, so these figures are zero rather than low"
                  : ""}
              </p>
            ) : null}
          </div>

          <HealthBreakdown
            assessment={assessment}
            onRefresh={() => refresh.mutate()}
            isRefreshing={refresh.isPending}
          />
        </div>
      ) : (
        <EmptyState message="Could not load your financial health assessment." />
      )}
    </div>
  );
}
