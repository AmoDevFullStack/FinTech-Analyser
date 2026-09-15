import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { RiskFlag } from "@/api/types";

export function useRiskFlags(status: "active" | "all" = "active") {
  return useQuery({
    queryKey: ["risk-flags", status],
    queryFn: () =>
      api.get<{ data: RiskFlag[] }>(`/risk-flags?status=${status}`).then((r) => r.data),
  });
}

export function useDismissRiskFlag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flagId: string) => api.post<RiskFlag>(`/risk-flags/${flagId}/dismiss`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-flags"] });
      // The dashboard shows a count of active flags, so it moves when one is dismissed.
      queryClient.invalidateQueries({ queryKey: ["position"] });
    },
  });
}

export function useAcknowledgeRiskFlag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flagId: string) => api.post<RiskFlag>(`/risk-flags/${flagId}/acknowledge`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["risk-flags"] }),
  });
}
