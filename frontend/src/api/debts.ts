import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Debt, DebtType, SchedulePeriod, StrategyComparison, WhatIfRow } from "@/api/types";

export function useDebts() {
  return useQuery({
    queryKey: ["debts"],
    queryFn: () => api.get<{ data: Debt[] }>("/debts").then((r) => r.data),
  });
}

export function useDebtSchedule(debtId: string, extraMonthly = "0") {
  return useQuery({
    queryKey: ["debts", debtId, "schedule", extraMonthly],
    queryFn: () =>
      api
        .get<{ data: SchedulePeriod[] }>(
          `/debts/${debtId}/schedule?extra_monthly=${encodeURIComponent(extraMonthly)}`,
        )
        .then((r) => r.data),
  });
}

export function useDebtWhatIf(debtId: string) {
  return useQuery({
    queryKey: ["debts", debtId, "what-if"],
    queryFn: () => api.get<{ data: WhatIfRow[] }>(`/debts/${debtId}/what-if`).then((r) => r.data),
  });
}

export function useDebtStrategies(totalMonthly?: string) {
  const query = totalMonthly ? `?total_monthly=${encodeURIComponent(totalMonthly)}` : "";
  return useQuery({
    queryKey: ["debts", "strategies", totalMonthly ?? "default"],
    queryFn: () => api.get<StrategyComparison>(`/debts/strategies${query}`),
  });
}

export interface CreateDebtInput {
  debt_type: DebtType;
  original_principal: string;
  current_balance: string;
  annual_rate: string;
  minimum_payment: string;
  started_on: string;
  // Kept as the raw string the field produced: parsing numbers is the API's job,
  // and src/lib/money.ts is the only place this tree may narrow a string to a number.
  term_months?: string;
  instalment?: string;
}

export function useCreateDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDebtInput) => api.post<Debt>("/debts", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["debts"] });
      // A debt change moves the health score, the dashboard total debt figure, and marks
      // the forecast stale — see DebtService._sync_position.
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
    },
  });
}

export interface UpdateDebtInput {
  debt_type?: DebtType;
  current_balance?: string;
  annual_rate?: string;
  minimum_payment?: string;
  instalment?: string;
  term_months?: string;
}

export function useUpdateDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ debtId, data }: { debtId: string; data: UpdateDebtInput }) =>
      api.patch<Debt>(`/debts/${debtId}`, data),
    onSuccess: (_debt, { debtId }) => {
      queryClient.invalidateQueries({ queryKey: ["debts"] });
      // Balance, rate, and payment all change the schedule and the strategy comparison,
      // not just the row — see DebtService._sync_position for the server side of this.
      queryClient.invalidateQueries({ queryKey: ["debts", debtId] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
    },
  });
}

export function useDeleteDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (debtId: string) => api.delete<void>(`/debts/${debtId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["debts"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
    },
  });
}
