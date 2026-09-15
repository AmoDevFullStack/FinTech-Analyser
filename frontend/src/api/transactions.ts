import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Transaction } from "@/api/types";

export interface TransactionFilters {
  accountId?: string;
  from?: string;
  to?: string;
  categoryId?: string;
  q?: string;
}

function toSearchParams(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  if (filters.accountId) params.set("account_id", filters.accountId);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.categoryId) params.set("category_id", filters.categoryId);
  if (filters.q) params.set("q", filters.q);
  return params.toString();
}

export function useTransactions(filters: TransactionFilters = {}) {
  const query = toSearchParams(filters);
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () =>
      api
        .get<{ data: Transaction[]; next_cursor: string | null }>(`/transactions?${query}`)
        .then((r) => r.data),
  });
}

export interface ImportSummary {
  batch_id: string;
  status: string;
  rows_parsed: number;
  rows_imported: number;
  rows_skipped_duplicate: number;
  rows_pending_conflict: number;
}

export function useUploadImport() {
  return useMutation({
    mutationFn: ({ accountId, file }: { accountId: string; file: File }) => {
      const form = new FormData();
      form.append("account_id", accountId);
      form.append("file", file);
      return api.postForm<ImportSummary>("/imports", form);
    },
  });
}

export function useCommitImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => api.post<ImportSummary>(`/imports/${batchId}/commit`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
    },
  });
}
