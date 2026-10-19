import { RefreshCw } from "lucide-react";

import { useCaptureSnapshot, usePosition } from "@/api/position";
import {
  AttentionRegion,
  CashFlowRegion,
  HealthRegion,
  PositionRegion,
  UpcomingRegion,
} from "@/features/dashboard";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { formatDateTime } from "@/lib/dates";

/** Route composition only — every figure comes from GET /position, per specs/dashboard.md.
 * `GET /position` never computes (ADR-003) — an account, transaction, or scenario change
 * recaptures the snapshot server-side, and this Refresh action covers everything else.
 */
export function Dashboard() {
  const { data: position, isLoading } = usePosition();
  const captureSnapshot = useCaptureSnapshot();

  if (isLoading) return <EmptyState message="Loading…" />;
  if (!position) return <EmptyState message="Could not load your position." />;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-title">Financial Digital Twin</h1>
          {position.as_of ? (
            <p className="text-caption text-content-tertiary">
              Position as of {formatDateTime(position.as_of)}
              {position.is_stale ? " · out of date" : ""}
            </p>
          ) : null}
          {/* What the monthly figures were measured over, and how much history stands
              behind them. A figure from one imported statement and a figure from eighteen
              months of them are different claims, and only one of them is worth acting on
              — saying which is cheaper than letting a reader assume. */}
          {position.months_of_history > 0 ? (
            <p className="text-caption text-content-tertiary">
              Monthly figures from your transactions
              {position.baseline_month ? ` · ${position.baseline_month}` : ""} ·{" "}
              {position.months_of_history}{" "}
              {position.months_of_history === 1 ? "month" : "months"} of history,{" "}
              {position.transactions_counted} transactions
            </p>
          ) : (
            <p className="text-caption text-content-tertiary">
              No transactions yet — upload a statement and these figures become real.
            </p>
          )}
        </div>
        <Button
          icon={RefreshCw}
          onClick={() => captureSnapshot.mutate()}
          disabled={captureSnapshot.isPending}
        >
          {captureSnapshot.isPending ? "Refreshing…" : "Refresh"}
        </Button>
      </header>
      <PositionRegion position={position} />
      <CashFlowRegion position={position} />
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <UpcomingRegion position={position} />
        <HealthRegion position={position} />
      </div>
      <AttentionRegion />
    </div>
  );
}
