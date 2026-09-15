import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { RecommendationRow } from "@/api/types";

export function useRecommendations() {
  return useQuery({
    queryKey: ["recommendations"],
    queryFn: () => api.get<{ data: RecommendationRow[] }>("/recommendations").then((r) => r.data),
  });
}

export function useDismissRecommendation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<RecommendationRow>(`/recommendations/${id}/dismiss`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });
}

export function useMarkActedOn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<RecommendationRow>(`/recommendations/${id}/acted-on`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });
}
