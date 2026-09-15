import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Scenario, ScenarioResult, VehiclePurchaseAssumptions } from "@/api/types";

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<{ data: Scenario[] }>("/scenarios").then((r) => r.data),
  });
}

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: ["scenarios", scenarioId],
    queryFn: () => api.get<Scenario>(`/scenarios/${scenarioId}`),
    enabled: Boolean(scenarioId),
  });
}

export interface CreateScenarioInput {
  name: string;
  description?: string;
  assumptions: VehiclePurchaseAssumptions;
}

export function useCreateScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateScenarioInput) =>
      api.post<Scenario>("/scenarios", { scenario_type: "vehicle_purchase", ...data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
  });
}

/** Running a scenario never invalidates ['position'] — it touches no real state, per
 * ADR-005 and docs/frontend.md §5.
 */
export function useRunScenario(scenarioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ScenarioResult>(`/scenarios/${scenarioId}/run`),
    onSuccess: (result) =>
      queryClient.setQueryData(["scenarios", scenarioId, "results"], result),
  });
}

export function useDeleteScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scenarioId: string) => api.delete<void>(`/scenarios/${scenarioId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
  });
}
