import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  MonthlySummaryResponse,
  PaymentMethod,
  SpendingInsight,
  SpendingPurpose,
  Transaction,
} from "@/api/types";

export interface TransactionFilters {
  accountId?: string;
  from?: string;
  to?: string;
  categoryId?: string;
  q?: string;
  /** Off turns the search back into a plain substring match. On — the default — also
   * returns rows whose description is within edit distance of the query. */
  fuzzy?: boolean;
  paymentMethod?: PaymentMethod;
  spendingPurpose?: SpendingPurpose;
  isRecurring?: boolean;
  uncategorisedOnly?: boolean;
}

function toSearchParams(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  if (filters.accountId) params.set("account_id", filters.accountId);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.categoryId) params.set("category_id", filters.categoryId);
  if (filters.q) params.set("q", filters.q);
  if (filters.fuzzy === false) params.set("fuzzy", "false");
  if (filters.paymentMethod) params.set("payment_method", filters.paymentMethod);
  if (filters.spendingPurpose) params.set("spending_purpose", filters.spendingPurpose);
  if (filters.isRecurring !== undefined) params.set("is_recurring", String(filters.isRecurring));
  if (filters.uncategorisedOnly) params.set("uncategorised_only", "true");
  return params.toString();
}

export interface TransactionSearchResponse {
  data: Transaction[];
  next_cursor: string | null;
  search: { q: string | null; fuzzy: boolean; min_score: string };
}

export function useTransactions(filters: TransactionFilters = {}) {
  const query = toSearchParams(filters);
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => api.get<TransactionSearchResponse>(`/transactions?${query}`),
  });
}

export interface MonthlySummaryFilters {
  /** `YYYY-MM-DD`. Widened to whole calendar months server-side. Omit both for the last
   * twelve months. */
  from?: string;
  to?: string;
  accountId?: string;
}

/** Month by month: what each one was, how it changed, and what the cash did.
 *
 * A query rather than a mutation, and cached under its own key, because the window is
 * part of the question — two windows are two different answers and neither invalidates
 * the other. Importing a statement does invalidate it, which is why `useCommitImport`
 * clears this key.
 */
export function useMonthlySummary(filters: MonthlySummaryFilters = {}) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.accountId) params.set("account_id", filters.accountId);
  const query = params.toString();

  return useQuery({
    queryKey: ["transactions", "months", filters],
    queryFn: () =>
      api.get<MonthlySummaryResponse>(`/transactions/months${query ? `?${query}` : ""}`),
  });
}

export interface ImportSummary {
  batch_id: string;
  status: string;
  rows_parsed: number;
  rows_imported: number;
  rows_skipped_duplicate: number;
  rows_pending_conflict: number;
  rows_merged: number;
  /** What the file was and what it moves. Present on the staging and commit responses. */
  insight?: SpendingInsight;
}

export function useUploadImport() {
  return useMutation({
    mutationFn: ({
      accountId,
      file,
      password,
    }: {
      accountId: string;
      file: File;
      /** For a password-protected statement PDF. Sent to open the file and never stored. */
      password?: string;
    }) => {
      const form = new FormData();
      form.append("account_id", accountId);
      form.append("file", file);
      if (password) form.append("password", password);
      return api.postForm<ImportSummary>("/imports", form);
    },
  });
}

export function useCommitImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => api.post<ImportSummary>(`/imports/${batchId}/commit`),
    onSuccess: () => {
      // ["transactions"] is a prefix of ["transactions", "months", ...], so the month
      // view is invalidated by this line too.
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
      // A commit records an `import.committed` event, and its handlers capture a snapshot,
      // reassess health, mark the forecast stale and re-evaluate risk — see
      // app/services/event_handlers.py.
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
      queryClient.invalidateQueries({ queryKey: ["risk-flags"] });
      queryClient.invalidateQueries({ queryKey: ["recurring"] });
    },
  });
}

export interface CreateTransactionInput {
  account_id: string;
  occurred_on: string;
  amount: string;
  description: string;
  category_id?: string;
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateTransactionInput) =>
      api.post<Transaction & { insight: SpendingInsight }>("/transactions", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
      queryClient.invalidateQueries({ queryKey: ["health-assessment"] });
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
    },
  });
}

export interface Classification {
  amount: string;
  payment_method: PaymentMethod;
  spending_purpose: SpendingPurpose;
  kind: string | null;
  merchant: string | null;
  method_confidence: string;
  purpose_confidence: string;
  matched_rule: string;
}

/** Read a description without storing anything — used to show what a manual entry will be
 * filed as before the user commits to it. */
export function useClassifyDescription() {
  return useMutation({
    mutationFn: (data: { description: string; amount: string }) =>
      api.post<Classification>("/transactions/classify", data),
  });
}
