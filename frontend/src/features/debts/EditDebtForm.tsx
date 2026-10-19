import { useState, type FormEvent } from "react";

import { useUpdateDebt, type UpdateDebtInput } from "@/api/debts";
import { ApiError } from "@/api/client";
import type { Debt, DebtType } from "@/api/types";
import { Button } from "@/components/Button";

import { DEBT_TYPES, isFixedTerm } from "./debtAppearance";

const FIELD_CLASSES =
  "h-11 rounded-md border border-rule bg-surface-raised px-3 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** Every value stays the string the input produced. docs/frontend.md §4: parsing a money
 * string into a number is the API's job, and src/lib/money.ts is the only place this tree
 * may narrow one at all. */
function initialState(debt: Debt) {
  return {
    debtType: debt.debt_type,
    currentBalance: debt.current_balance as string,
    annualRate: debt.annual_rate as string,
    minimumPayment: debt.minimum_payment as string,
    instalment: (debt.instalment as string | null) ?? "",
    termMonths: debt.term_months === null ? "" : String(debt.term_months),
  };
}

export function EditDebtForm({ debt, onDone }: { debt: Debt; onDone: () => void }) {
  const [form, setForm] = useState(() => initialState(debt));
  const update = useUpdateDebt();

  function set<K extends keyof ReturnType<typeof initialState>>(
    key: K,
    value: ReturnType<typeof initialState>[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    // Only changed fields are sent. The PATCH treats an omitted field as "leave alone"
    // (UpdateDebtRequest), so sending everything would rewrite values the user did not
    // touch — harmless today, but it is also what makes "supply at least one field to
    // change" a real check rather than one this form always satisfies by accident.
    const initial = initialState(debt);
    const data: UpdateDebtInput = {};
    if (form.debtType !== initial.debtType) data.debt_type = form.debtType;
    if (form.currentBalance !== initial.currentBalance) data.current_balance = form.currentBalance;
    if (form.annualRate !== initial.annualRate) data.annual_rate = form.annualRate;
    if (form.minimumPayment !== initial.minimumPayment) data.minimum_payment = form.minimumPayment;
    if (form.instalment !== initial.instalment && form.instalment !== "") {
      data.instalment = form.instalment;
    }
    if (form.termMonths !== initial.termMonths) data.term_months = form.termMonths;

    if (Object.keys(data).length === 0) {
      onDone();
      return;
    }

    update.mutate({ debtId: debt.id, data }, { onSuccess: onDone });
  }

  const fixedTerm = isFixedTerm(form.debtType);
  const fieldErrors = update.error instanceof ApiError ? update.error.fieldErrors : {};

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 border-t border-rule pt-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Type</span>
          <select
            className={FIELD_CLASSES}
            value={form.debtType}
            onChange={(e) => set("debtType", e.target.value as DebtType)}
          >
            {DEBT_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Current balance</span>
          <input
            className={FIELD_CLASSES}
            inputMode="decimal"
            required
            value={form.currentBalance}
            onChange={(e) => set("currentBalance", e.target.value)}
          />
          {fieldErrors.current_balance ? (
            <span className="text-caption text-signal-critical">
              {fieldErrors.current_balance}
            </span>
          ) : null}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">
            Annual rate, as a decimal (0.24 for 24%)
          </span>
          <input
            className={FIELD_CLASSES}
            inputMode="decimal"
            required
            value={form.annualRate}
            onChange={(e) => set("annualRate", e.target.value)}
          />
          {fieldErrors.annual_rate ? (
            <span className="text-caption text-signal-critical">{fieldErrors.annual_rate}</span>
          ) : null}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Minimum monthly payment</span>
          <input
            className={FIELD_CLASSES}
            inputMode="decimal"
            required
            value={form.minimumPayment}
            onChange={(e) => set("minimumPayment", e.target.value)}
          />
          {fieldErrors.minimum_payment ? (
            <span className="text-caption text-signal-critical">
              {fieldErrors.minimum_payment}
            </span>
          ) : null}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">
            Contractual instalment (optional)
          </span>
          <input
            className={FIELD_CLASSES}
            inputMode="decimal"
            value={form.instalment}
            onChange={(e) => set("instalment", e.target.value)}
            placeholder="Defaults to the minimum payment"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">
            Term in months {fixedTerm ? "" : "(blank for a revolving facility)"}
          </span>
          <input
            className={FIELD_CLASSES}
            inputMode="numeric"
            value={form.termMonths}
            onChange={(e) => set("termMonths", e.target.value)}
            placeholder={fixedTerm ? "72" : ""}
          />
          {fieldErrors.term_months ? (
            <span className="text-caption text-signal-critical">{fieldErrors.term_months}</span>
          ) : null}
        </label>
      </div>

      {update.isError ? (
        <p className="text-caption text-signal-critical">
          Could not save the change: {(update.error as Error).message}
        </p>
      ) : null}

      <div className="flex justify-end gap-3">
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
