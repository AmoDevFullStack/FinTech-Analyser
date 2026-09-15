import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { FundingPlan, Goal, GoalProgress } from "@/api/types";

export function useGoals() {
  return useQuery({
    queryKey: ["goals"],
    queryFn: () => api.get<{ data: Goal[] }>("/goals").then((r) => r.data),
  });
}

export function useGoalProgress(goalId: string) {
  return useQuery({
    queryKey: ["goals", goalId, "progress"],
    queryFn: () => api.get<GoalProgress>(`/goals/${goalId}/progress`),
  });
}

export function useFundingPlan() {
  return useQuery({
    queryKey: ["goals", "funding-plan"],
    queryFn: () => api.get<FundingPlan>("/goals/funding-plan"),
  });
}

export interface CreateGoalInput {
  name: string;
  target_amount: string;
  target_date: string;
  priority?: string;
  account_id?: string;
  opening_amount?: string;
  planned_monthly_contribution?: string;
}

export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateGoalInput) => api.post<Goal>("/goals", data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["goals"] }),
  });
}

export function useRecordContribution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      goalId,
      amount,
      occurredOn,
    }: {
      goalId: string;
      amount: string;
      occurredOn?: string;
    }) =>
      api.post<unknown>(`/goals/${goalId}/contributions`, {
        amount,
        occurred_on: occurredOn,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["goals"] }),
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => api.delete<void>(`/goals/${goalId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["goals"] }),
  });
}
