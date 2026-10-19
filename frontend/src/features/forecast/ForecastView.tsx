import { RefreshCw } from "lucide-react";

import { useForecast, useForecastAccuracy, useRefreshForecast } from "@/api/forecasts";
import type { ForecastResponse } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { ProjectedValue } from "@/components/ProjectedValue";
import { formatDateTime } from "@/lib/dates";
import { formatRateAsPercent } from "@/lib/money";

function hasForecast(
  data: ForecastResponse | { forecast: null } | undefined,
): data is ForecastResponse {
  return Boolean(data && "id" in data);
}

/** Every figure here is a projection, so each is rendered through ProjectedValue, which
 * cannot display a value without its generation date (docs/frontend.md §6, ADR-003).
 * Staleness and low confidence are stated as labelled chips, not colour.
 */
export function ForecastView() {
  const { data, isLoading } = useForecast();
  const refresh = useRefreshForecast();

  if (isLoading) {
    return (
      <Card>
        <EmptyState message="Loading…" />
      </Card>
    );
  }

  if (!hasForecast(data)) {
    return (
      <Card>
        <h2 className="text-title">Forecast</h2>
        <EmptyState message="No forecast has been generated yet." />
        <div>
          <Button
            icon={RefreshCw}
            variant="primary"
            onClick={() => refresh.mutate({})}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? "Generating…" : "Generate a forecast"}
          </Button>
        </div>
      </Card>
    );
  }

  const milestones = [11, 23, 59]
    .map((index) => data.periods[index])
    .filter((period) => period !== undefined);

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-title">Forecast</h2>
        <div className="flex gap-2">
          {data.is_stale ? (
            <Chip>Out of date — your figures have changed since this was worked out</Chip>
          ) : null}
          {data.is_low_confidence ? (
            <Chip>Less certain — based on {data.months_observed} months of history</Chip>
          ) : null}
        </div>
      </div>

      <p className="text-caption text-content-tertiary">
        Worked out {formatDateTime(data.generated_at)}.
        Inflation {formatRateAsPercent(data.assumptions.inflation_annual as never)}, salary
        growth {formatRateAsPercent(data.assumptions.salary_growth_annual as never)}. These
        are assumptions, not facts.
      </p>

      <div className="flex flex-wrap gap-8">
        {milestones.map((period) => (
          <div key={period.month} className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">
              Net worth at {period.month}
            </span>
            <ProjectedValue
              projected={{
                value: period.net_worth,
                generatedAt: data.generated_at,
                isStale: data.is_stale,
              }}
            />
          </div>
        ))}
      </div>

      <div>
        <Button icon={RefreshCw} onClick={() => refresh.mutate({})} disabled={refresh.isPending}>
          {refresh.isPending ? "Regenerating…" : "Regenerate"}
        </Button>
      </div>
    </Card>
  );
}

/** specs/forecasting.md: "A forecasting product that never checks itself is a horoscope."
 * This is the check, shown to the user rather than kept internal.
 */
export function ForecastAccuracyView() {
  const { data, isLoading } = useForecastAccuracy();

  if (isLoading) {
    return (
      <Card>
        <EmptyState message="Loading…" />
      </Card>
    );
  }

  const measured = (data?.summaries ?? []).filter((summary) => summary.months_measured > 0);
  if (measured.length === 0) {
    return (
      <Card>
        <h2 className="text-title">How accurate this has been</h2>
        <EmptyState message="No month has been measured yet. Accuracy appears once a projected month has passed and its actuals are in." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">How accurate this has been</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead>
            <tr className="bg-surface-sunken text-left text-label text-content-secondary">
              <th className="p-3 font-medium">Metric</th>
              <th className="p-3 text-right font-medium">Months measured</th>
              <th className="p-3 text-right font-medium">Average error</th>
              <th className="p-3 font-medium">Bias</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {measured.map((summary) => (
              <tr key={summary.metric}>
                <td className="p-3">{summary.metric.replace(/_/g, " ")}</td>
                <td className="p-3 text-right tabular-nums">{summary.months_measured}</td>
                <td className="p-3 text-right tabular-nums">R{summary.mean_absolute_error}</td>
                <td className="p-3">
                  {summary.has_persistent_bias
                    ? `Consistently ${summary.bias_direction?.replace(/_/g, " ")}`
                    : "No persistent bias"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
