import { RefreshCw } from "lucide-react";

import { Button } from "@/components/Button";
import { ScoreGauge } from "@/components/ScoreGauge";
import { formatDateTime } from "@/lib/dates";
import { asRate, formatRateAsPercent, scoreAsNumber } from "@/lib/money";
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
        <ScoreGauge value={assessment.score} size={128} label="Financial health score" />
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
            <ScoreGauge
              value={scoreAsNumber(component.score)}
              size={56}
              label={healthComponentLabel(component.name)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
