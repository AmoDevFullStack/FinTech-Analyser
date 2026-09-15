import { Link } from "react-router-dom";

import { useScenarios } from "@/api/scenarios";
import { EmptyState } from "@/components/EmptyState";
import { formatDateTime } from "@/lib/dates";

export function ScenarioList() {
  const { data: scenarios, isLoading } = useScenarios();

  if (isLoading) return <EmptyState message="Loading scenarios…" />;
  if (!scenarios || scenarios.length === 0) {
    return <EmptyState message="No scenarios yet. Create one below." />;
  }

  return (
    <ul className="flex flex-col divide-y divide-rule">
      {scenarios.map((scenario) => (
        <li key={scenario.id} className="flex items-center justify-between py-3">
          <div className="flex flex-col gap-0.5">
            <Link to={`/scenarios/${scenario.id}`} className="text-body font-medium text-accent">
              {scenario.name}
            </Link>
            <span className="text-caption text-content-tertiary">
              Snapshot from {formatDateTime(scenario.snapshot_captured_at)}
            </span>
          </div>
          <span className="text-label text-content-secondary">{scenario.status}</span>
        </li>
      ))}
    </ul>
  );
}
