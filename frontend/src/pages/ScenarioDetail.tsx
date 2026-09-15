import { Play } from "lucide-react";
import { useParams } from "react-router-dom";

import { useRunScenario, useScenario } from "@/api/scenarios";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ScenarioResultView } from "@/features/scenarios";
import { formatDateTime } from "@/lib/dates";

export function ScenarioDetail() {
  const { scenarioId = "" } = useParams();
  const { data: scenario, isLoading } = useScenario(scenarioId);
  const run = useRunScenario(scenarioId);

  if (isLoading) return <EmptyState message="Loading…" />;
  if (!scenario) return <EmptyState message="Scenario not found." />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-title">{scenario.name}</h1>
          <p className="text-caption text-content-tertiary">
            Snapshot from {formatDateTime(scenario.snapshot_captured_at)}
          </p>
        </div>
        <Button variant="primary" icon={Play} onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? "Running…" : "Run scenario"}
        </Button>
      </header>
      {run.data ? (
        <ScenarioResultView result={run.data} />
      ) : (
        <EmptyState message="Run the scenario to see its impact against your baseline." />
      )}
    </div>
  );
}
