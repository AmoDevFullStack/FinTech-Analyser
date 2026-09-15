import { Link } from "react-router-dom";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import type { Position } from "@/api/types";
import { healthComponentLabel } from "./healthComponentLabels";

/** Region 4 — financial health score with trajectory. See specs/dashboard.md: "Score
 * with trajectory arrow, and the single largest contributing factor. The full breakdown
 * is one click away, not on the page."
 */
export function HealthRegion({ position }: { position: Position }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-title">Financial health</h2>
        {position.health_generated_at ? (
          <span className="text-caption text-content-tertiary">
            Assessed {formatShortDate(position.health_generated_at)}
          </span>
        ) : null}
      </div>

      {position.health_score === null ? (
        <EmptyState message="Not yet assessed." />
      ) : (
        <>
          <div className="flex items-baseline gap-3">
            <span className="text-position tabular-nums">{position.health_score}</span>
            <span className="text-body text-content-secondary">of 100</span>
            {position.health_score_change !== null ? (
              <TrendArrow change={position.health_score_change} />
            ) : null}
          </div>

          {position.health_largest_negative_contributor ? (
            <div className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">
                Largest drag on the score
              </span>
              <p className="text-body">
                {healthComponentLabel(position.health_largest_negative_contributor)}.
              </p>
            </div>
          ) : null}

          <Link to="/health" className="text-label text-accent w-fit">
            See all components
          </Link>
        </>
      )}
    </Card>
  );
}

function TrendArrow({ change }: { change: number }) {
  if (change === 0) {
    return <span className="text-label text-content-tertiary">Unchanged since last assessment</span>;
  }
  const up = change > 0;
  return (
    <span
      className={`inline-flex items-center gap-1 text-label font-medium ${up ? "text-signal-positive" : "text-signal-caution"}`}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {up ? <path d="M12 19V5M5 12l7-7 7 7" /> : <path d="M12 5v14M5 12l7 7 7-7" />}
      </svg>
      {up ? "Up" : "Down"} {Math.abs(change)} since last assessment
    </span>
  );
}

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short" });
}
