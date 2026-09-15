import { RefreshCw } from "lucide-react";

import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { formatDateTime } from "@/lib/dates";
import { asRate, formatRateAsPercent } from "@/lib/money";
import type { HealthAssessment } from "@/api/types";
import { healthComponentLabel } from "./healthComponentLabels";

/** Every component has a stated formula and band table (specs/financial-health.md) — this
 * is where a user interrogates the score component by component, per requirement 10.
 */
export function HealthBreakdown({
  assessment,
  onRefresh,
  isRefreshing,
}: {
  assessment: HealthAssessment;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <span className="text-position tabular-nums">{assessment.score}</span>
          <span className="text-body text-content-secondary">of 100</span>
        </div>
        <Button icon={RefreshCw} onClick={onRefresh} disabled={isRefreshing}>
          {isRefreshing ? "Refreshing…" : "Refresh assessment"}
        </Button>
      </header>
      <p className="text-caption text-content-tertiary">
        Assessed {formatDateTime(assessment.computed_at)} · weights v{assessment.weights_version}
      </p>
      <p className="text-body text-content-secondary">
        An assessment of financial resilience — how well you would withstand a setback —
        not a credit score and not a judgement.
      </p>

      <div className="flex flex-col divide-y divide-rule">
        {assessment.components.map((component) => (
          <div key={component.name} className="flex items-center justify-between gap-4 py-4">
            <div className="flex flex-col gap-1">
              <span className="text-body font-medium">{healthComponentLabel(component.name)}</span>
              <span className="text-caption text-content-tertiary">
                Ratio {formatRateAsPercent(asRate(component.ratio))} · weight{" "}
                {formatRateAsPercent(asRate(component.weight))}
              </span>
            </div>
            <Card className="w-24 items-center gap-0 p-3">
              <span className="text-figure tabular-nums">{component.score}</span>
              <span className="text-caption text-content-tertiary">/ 100</span>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
}
