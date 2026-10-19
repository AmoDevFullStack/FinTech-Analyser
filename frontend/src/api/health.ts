import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/api/client";
import type { HealthAssessment } from "@/api/types";

/** One month's assessment. No month asks for the most recent one, which is what the page
 * opens on.
 *
 * 404 (no assessment yet) is a legitimate empty state, not an error to surface — see
 * specs/dashboard.md's empty-state rule for a section with no stored result yet.
 */
export function useHealthAssessment(month?: string) {
  return useQuery({
    queryKey: ["health-assessment", month ?? "latest"],
    queryFn: () =>
      api.get<HealthAssessment>(
        month ? `/health-assessment?month=${month}` : "/health-assessment",
      ),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 1,
  });
}

/** The score month by month, oldest first — the series a trajectory is read from. */
export function useHealthMonths() {
  return useQuery({
    queryKey: ["health-assessment", "months"],
    queryFn: () =>
      api
        .get<{ data: HealthAssessment[]; months: number }>("/health-assessment/months")
        .then((r) => r.data),
  });
}

export function useRefreshHealthAssessment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<HealthAssessment>("/health-assessment/refresh"),
    onSuccess: () => {
      // A refresh re-scores several months, so every month's entry is invalidated rather
      // than the returned one being written into the cache. Writing it would leave the
      // other months showing scores the refresh has just superseded.
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
    },
  });
}
