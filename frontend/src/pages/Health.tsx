import { Play } from "lucide-react";
import { Link } from "react-router-dom";

import { useHealthAssessment, useRefreshHealthAssessment } from "@/api/health";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { HealthBreakdown } from "@/features/dashboard";

export function Health() {
  const { data: assessment, isLoading, error } = useHealthAssessment();
  const refresh = useRefreshHealthAssessment();

  const notYetAssessed = error instanceof ApiError && error.status === 404;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-title">Financial health</h1>
        <Link to="/" className="text-label text-accent">
          Back to dashboard
        </Link>
      </div>

      {isLoading ? (
        <EmptyState message="Loading…" />
      ) : notYetAssessed ? (
        <div className="flex flex-col gap-4">
          <EmptyState message="Not yet assessed." />
          <Button
            variant="primary"
            icon={Play}
            className="w-fit"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? "Assessing…" : "Run first assessment"}
          </Button>
        </div>
      ) : assessment ? (
        <HealthBreakdown
          assessment={assessment}
          onRefresh={() => refresh.mutate()}
          isRefreshing={refresh.isPending}
        />
      ) : (
        <EmptyState message="Could not load your financial health assessment." />
      )}
    </div>
  );
}
