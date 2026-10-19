import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { useAccounts } from "@/api/accounts";
import { ApiError } from "@/api/client";
import { useClassifyDescription, useCreateTransaction } from "@/api/transactions";
import type { SpendingInsight } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";

import { ImpactSummary } from "./ImpactSummary";
import {
  PAYMENT_METHOD_LABELS,
  SPEND_KIND_LABELS,
  SPENDING_PURPOSE_LABELS,
} from "./spendingLabels";

const FIELD_CLASSES =
  "h-11 rounded-md border border-rule bg-surface-raised px-3 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/**
 * One transaction, entered by hand.
 *
 * specs/transactions.md lists manual entry as an input alongside CSV, and a user whose
 * landlord is paid by EFT from an account they have not connected has no other way to get
 * their rent into the system. Without it the largest line in their budget is invisible and
 * every figure derived from essential spending is wrong by that amount.
 *
 * The detection preview updates as the description is typed, through
 * `POST /transactions/classify`, which stores nothing. Showing what a payment will be
 * filed as before it is saved is cheaper for everyone than a correction afterwards.
 */
export function AddTransactionForm() {
  const { data: accounts } = useAccounts();
  const [accountId, setAccountId] = useState("");
  const [occurredOn, setOccurredOn] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [insight, setInsight] = useState<SpendingInsight | null>(null);

  const classify = useClassifyDescription();
  const create = useCreateTransaction();
  const { mutate: classifyMutate, reset: resetClassification } = classify;

  useEffect(() => {
    if (description.trim().length < 3 || amount.trim() === "") {
      resetClassification();
      return;
    }
    // Debounced: every keystroke would otherwise be a round trip, and the answer only
    // changes when the description settles.
    const timer = window.setTimeout(() => {
      classifyMutate({ description, amount });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [description, amount, classifyMutate, resetClassification]);

  const detected = classify.data;
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};

  return (
    <Card>
      <h2 className="text-title">Add a payment</h2>
      <p className="text-caption text-content-tertiary">
        For anything your statements do not carry — rent paid from another account, cash, a
        transfer someone made to you.
      </p>

      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate(
            {
              account_id: accountId,
              occurred_on: occurredOn,
              // The raw string the field produced. Parsing money is the API's job —
              // docs/frontend.md §4.
              amount,
              description,
            },
            {
              onSuccess: (created) => {
                setInsight(created.insight);
                setAmount("");
                setDescription("");
              },
            },
          );
        }}
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Account</span>
            <select
              className={FIELD_CLASSES}
              required
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">Select…</option>
              {accounts?.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Date</span>
            <input
              className={FIELD_CLASSES}
              type="date"
              required
              value={occurredOn}
              onChange={(e) => setOccurredOn(e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">
              Amount — negative for money out
            </span>
            <input
              className={FIELD_CLASSES}
              inputMode="decimal"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="-14500.00"
            />
            {fieldErrors.amount ? (
              <span className="text-caption text-signal-critical">{fieldErrors.amount}</span>
            ) : null}
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Description</span>
            <input
              className={FIELD_CLASSES}
              required
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Rent — 14 Bree Street"
            />
            {fieldErrors.description ? (
              <span className="text-caption text-signal-critical">
                {fieldErrors.description}
              </span>
            ) : null}
          </label>
        </div>

        {detected ? (
          <p className="flex flex-wrap items-center gap-2 text-caption text-content-secondary">
            Read as
            <Chip>{SPENDING_PURPOSE_LABELS[detected.spending_purpose]}</Chip>
            <Chip>{PAYMENT_METHOD_LABELS[detected.payment_method]}</Chip>
            {detected.kind ? (
              <Chip>
                {SPEND_KIND_LABELS[detected.kind as keyof typeof SPEND_KIND_LABELS] ??
                  detected.kind}
              </Chip>
            ) : null}
            {detected.spending_purpose === "unknown" ? (
              <span>— you can set a category after saving.</span>
            ) : null}
          </p>
        ) : null}

        {create.isError ? (
          <p className="text-caption text-signal-critical">
            Could not save the payment: {(create.error as Error).message}
          </p>
        ) : null}

        <div>
          <Button type="submit" variant="primary" icon={Plus} disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Add payment"}
          </Button>
        </div>
      </form>

      {insight ? <ImpactSummary insight={insight} heading="What this changed" /> : null}
    </Card>
  );
}
