import { useState } from "react";

import { useTransactions } from "@/api/transactions";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { asMoney } from "@/lib/money";

export function TransactionList() {
  const [q, setQ] = useState("");
  const { data: transactions, isLoading } = useTransactions({ q: q || undefined });

  return (
    <div className="flex flex-col gap-4">
      <input
        placeholder="Search description…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="h-11 max-w-sm rounded-md border border-rule bg-surface-raised px-3 text-body"
      />
      {isLoading ? (
        <EmptyState message="Loading transactions…" />
      ) : !transactions || transactions.length === 0 ? (
        <EmptyState message="No transactions yet. Import a CSV to get started." />
      ) : (
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-rule bg-surface-sunken text-left text-label text-content-secondary">
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn) => (
              <tr key={txn.id} className="border-b border-rule">
                <td className="px-3 py-2 text-caption text-content-tertiary">
                  {formatDate(txn.occurred_on)}
                </td>
                <td className="px-3 py-2">{txn.description}</td>
                <td className="px-3 py-2 text-right">
                  <MoneyText value={asMoney(txn.amount)} size="body" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
