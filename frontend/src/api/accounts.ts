import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Account, AccountType } from "@/api/types";

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get<{ data: Account[] }>("/accounts").then((r) => r.data),
  });
}

export interface CreateAccountInput {
  name: string;
  account_type: AccountType;
  institution?: string;
  opening_balance: string;
  opened_on?: string;
  interest_rate?: string;
  credit_limit?: string;
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateAccountInput) => api.post<Account>("/accounts", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      // The backend recaptures a position snapshot AND reassesses financial health on any
      // account change that moves a figure (AccountService._sync_position) — invalidate
      // both so the dashboard and the health page pick them up without a manual reload.
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      // A new or changed account changes which transactions a month covers.
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}

export function useArchiveAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: string) => api.post<Account>(`/accounts/${accountId}/archive`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      // The backend recaptures a position snapshot AND reassesses financial health on any
      // account change that moves a figure (AccountService._sync_position) — invalidate
      // both so the dashboard and the health page pick them up without a manual reload.
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      // A new or changed account changes which transactions a month covers.
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}

export interface UpdateAccountInput {
  name?: string;
  institution?: string;
  opened_on?: string;
  interest_rate?: string;
  credit_limit?: string;
  balance?: string;
}

export function useUpdateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, data }: { accountId: string; data: UpdateAccountInput }) =>
      api.patch<Account>(`/accounts/${accountId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      // The backend recaptures a position snapshot AND reassesses financial health on any
      // account change that moves a figure (AccountService._sync_position) — invalidate
      // both so the dashboard and the health page pick them up without a manual reload.
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      // A new or changed account changes which transactions a month covers.
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}
