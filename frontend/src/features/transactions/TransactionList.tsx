import { Search, Sparkles } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { useTransactions, type TransactionFilters } from "@/api/transactions";
import type { SpendingPurpose, Transaction } from "@/api/types";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { asMoney } from "@/lib/money";

import { PAYMENT_METHOD_LABELS, SPENDING_PURPOSE_LABELS } from "./spendingLabels";

const FIELD_CLASSES =
  "h-11 rounded-md border border-rule bg-surface-raised px-3 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** The purposes worth putting in a filter list. The full taxonomy has twenty-seven
 * members and a select with twenty-seven options is a worse way to find rent than typing
 * "rent" into the search box. */
const FILTERABLE_PURPOSES: SpendingPurpose[] = [
  "rent",
  "bond_repayment",
  "utilities",
  "groceries",
  "fuel",
  "transport",
  "insurance",
  "medical",
  "telecoms",
  "subscriptions",
  "dining",
  "education",
  "debt_repayment",
  "savings",
  "salary",
  "unknown",
];

function DetectionChips({ transaction }: { transaction: Transaction }) {
  // Null means the row predates detection and has not been reclassified — rendered as
  // nothing rather than as "unknown", because "not looked at" and "looked at and could
  // not tell" are different claims and only the second is worth a user's attention.
  if (transaction.payment_method === null && transaction.spending_purpose === null) {
    return null;
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {transaction.spending_purpose ? (
        <Chip>{SPENDING_PURPOSE_LABELS[transaction.spending_purpose]}</Chip>
      ) : null}
      {transaction.payment_method ? (
        <Chip>{PAYMENT_METHOD_LABELS[transaction.payment_method]}</Chip>
      ) : null}
    </span>
  );
}

export function TransactionList() {
  const [q, setQ] = useState("");
  const [fuzzy, setFuzzy] = useState(true);
  const [purpose, setPurpose] = useState<SpendingPurpose | "">("");

  // The fuzzy search ranks in the application rather than the database, so every
  // keystroke is real work. Deferring keeps typing responsive without debouncing by hand.
  const deferredQ = useDeferredValue(q);

  const filters: TransactionFilters = {
    q: deferredQ || undefined,
    fuzzy,
    spendingPurpose: purpose || undefined,
  };
  const { data, isLoading } = useTransactions(filters);
  const transactions = data?.data;
  const fuzzyActive = data?.search.fuzzy ?? false;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Search</span>
          <span className="relative">
            <Search
              size={16}
              strokeWidth={2}
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
            />
            <input
              placeholder="Merchant or description…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={`${FIELD_CLASSES} w-72 pl-9`}
            />
          </span>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Spent on</span>
          <select
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as SpendingPurpose | "")}
            className={FIELD_CLASSES}
          >
            <option value="">Anything</option>
            {FILTERABLE_PURPOSES.map((value) => (
              <option key={value} value={value}>
                {SPENDING_PURPOSE_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex h-11 items-center gap-2 text-label text-content-secondary">
          <input
            type="checkbox"
            checked={fuzzy}
            onChange={(e) => setFuzzy(e.target.checked)}
            className="h-4 w-4"
          />
          Match close spellings
        </label>
      </div>

      {fuzzyActive ? (
        <p className="flex items-center gap-2 text-caption text-content-tertiary">
          <Sparkles size={14} strokeWidth={2} aria-hidden="true" />
          Also showing descriptions close to “{deferredQ}”. Rows marked “close match” are
          not an exact hit.
        </p>
      ) : null}

      {isLoading ? (
        <EmptyState message="Loading transactions…" />
      ) : !transactions || transactions.length === 0 ? (
        <EmptyState
          message={
            deferredQ
              ? `Nothing matches “${deferredQ}”. Turning on “match close spellings” widens the search.`
              : "No transactions yet. Import a CSV to get started."
          }
        />
      ) : (
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-rule bg-surface-sunken text-left text-label text-content-secondary">
              <th scope="col" className="px-3 py-2">
                Date
              </th>
              <th scope="col" className="px-3 py-2">
                Description
              </th>
              <th scope="col" className="px-3 py-2">
                Detected as
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn) => (
              <tr key={txn.id} className="border-b border-rule">
                <td className="px-3 py-2 text-caption text-content-tertiary">
                  {formatDate(txn.occurred_on)}
                </td>
                <td className="px-3 py-2">
                  <span className="flex flex-col gap-0.5">
                    <span>{txn.description}</span>
                    {txn.match_basis === "fuzzy" ? (
                      <span className="text-caption text-content-tertiary">Close match</span>
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <DetectionChips transaction={txn} />
                </td>
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
