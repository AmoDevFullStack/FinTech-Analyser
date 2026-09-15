import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/api/client";
import type { HealthAssessment } from "@/api/types";

/** 404 (no assessment yet) is a legitimate empty state, not an error to surface — see
 * specs/dashboard.md's empty-state rule for a section with no stored result yet.
 */
export function useHealthAssessment() {
  return useQuery({
    queryKey: ["health-assessment"],
    queryFn: () => api.get<HealthAssessment>("/health-assessment"),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 1,
  });
}

export function useHealthHistory() {
  return useQuery({
    queryKey: ["health-assessment", "history"],
    queryFn: () =>
      api.get<{ data: HealthAssessment[] }>("/health-assessment/history").then((r) => r.data),
  });
}

export function useRefreshHealthAssessment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<HealthAssessment>("/health-assessment/refresh"),
    onSuccess: (assessment) => {
      queryClient.setQueryData(["health-assessment"], assessment);
      queryClient.invalidateQueries({ queryKey: ["health-assessment", "history"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
    },
  });
}
