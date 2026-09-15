import { AlertTriangle } from "lucide-react";

import { useAcknowledgeRiskFlag, useDismissRiskFlag, useRiskFlags } from "@/api/riskFlags";
import type { RiskFlag, RiskSeverity } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { formatDate } from "@/lib/dates";

const SEVERITY_LABELS: Record<RiskSeverity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const RISK_TYPE_LABELS: Record<string, string> = {
  cash_flow_shortfall: "Projected cash-flow shortfall",
  obligation_coverage_gap: "Obligation coverage gap",
  emergency_reserve_depletion: "Emergency reserve depletion",
  debt_burden_threshold: "Debt burden",
  anomalous_spending: "Spending above baseline",
  credit_utilisation: "Credit utilisation",
};

/** The explanation text comes from the server, already written to the spec's copy
 * conventions — a figure and a date, never a characterisation of the person. It is
 * rendered verbatim rather than being reworded here, so there is one place that copy
 * lives and one place to review it.
 *
 * Severity is carried by a labelled chip, never by colour alone (design-system §2.3).
 */
function RiskFlagRow({ flag }: { flag: RiskFlag }) {
  const dismiss = useDismissRiskFlag();
  const acknowledge = useAcknowledgeRiskFlag();

  return (
    <li className="flex flex-col gap-3 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="text-body font-medium">
          {RISK_TYPE_LABELS[flag.risk_type] ?? flag.risk_type}
        </span>
        <Chip icon={AlertTriangle}>{SEVERITY_LABELS[flag.severity]}</Chip>
      </div>

      <p className="text-body text-content-secondary">{flag.explanation}</p>

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-caption text-content-tertiary">
          {flag.projected_date ? `Materialises ${formatDate(flag.projected_date)} · ` : ""}
          Detected {formatDate(flag.detected_on)} · from {flag.computation_reference}
        </span>
      </div>

      <div className="flex gap-3">
        <Button onClick={() => acknowledge.mutate(flag.id)} disabled={acknowledge.isPending}>
          Acknowledge
        </Button>
        <Button onClick={() => dismiss.mutate(flag.id)} disabled={dismiss.isPending}>
          Dismiss for 30 days
        </Button>
      </div>
    </li>
  );
}

export function RiskFlagList() {
  const { data: flags, isLoading } = useRiskFlags("active");

  if (isLoading) {
    return (
      <Card>
        <EmptyState message="Loading…" />
      </Card>
    );
  }

  // specs/dashboard.md: this region is ABSENT rather than showing a green all-clear,
  // so it never trains the user to skim past it.
  if (!flags || flags.length === 0) return null;

  return (
    <Card>
      <h2 className="text-title">Attention</h2>
      <ul className="flex flex-col divide-y divide-rule">
        {flags.map((flag) => (
          <RiskFlagRow key={flag.id} flag={flag} />
        ))}
      </ul>
    </Card>
  );
}
