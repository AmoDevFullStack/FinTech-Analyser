import { useState } from "react";

import { useCreateDebt } from "@/api/debts";
import type { DebtType } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

import { DEBT_TYPES, isFixedTerm } from "./debtAppearance";

const FIELD_CLASS =
  "rounded border border-rule bg-surface px-3 py-2 text-body text-content focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent";

export function CreateDebtForm() {
  const createDebt = useCreateDebt();
  const [debtType, setDebtType] = useState<DebtType>("credit_card");
  const [balance, setBalance] = useState("");
  const [rate, setRate] = useState("");
  const [minimumPayment, setMinimumPayment] = useState("");
  const [termMonths, setTermMonths] = useState("");
  const [startedOn, setStartedOn] = useState("");

  const fixedTerm = isFixedTerm(debtType);

  return (
    <Card>
      <h2 className="text-title">Add a debt</h2>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          createDebt.mutate(
            {
              debt_type: debtType,
              // The opening principal is the current balance unless the user is recording
              // a debt part-way through; there is no separate field for it here because
              // an approximate original principal would show up in no figure that matters.
              original_principal: balance,
              current_balance: balance,
              annual_rate: rate,
              minimum_payment: minimumPayment,
              started_on: startedOn,
              term_months: termMonths || undefined,
            },
            {
              onSuccess: () => {
                setBalance("");
                setRate("");
                setMinimumPayment("");
                setTermMonths("");
                setStartedOn("");
              },
            },
          );
        }}
      >
        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Type
          <select
            className={FIELD_CLASS}
            value={debtType}
            onChange={(event) => setDebtType(event.target.value as DebtType)}
          >
            {DEBT_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Current balance
          <input
            className={FIELD_CLASS}
            inputMode="decimal"
            required
            value={balance}
            onChange={(event) => setBalance(event.target.value)}
            placeholder="20000.00"
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Annual rate, as a decimal (0.24 for 24%)
          <input
            className={FIELD_CLASS}
            inputMode="decimal"
            required
            value={rate}
            onChange={(event) => setRate(event.target.value)}
            placeholder="0.24"
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Minimum monthly payment
          <input
            className={FIELD_CLASS}
            inputMode="decimal"
            required
            value={minimumPayment}
            onChange={(event) => setMinimumPayment(event.target.value)}
            placeholder="600.00"
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Term in months {fixedTerm ? "" : "(leave blank for a revolving facility)"}
          <input
            className={FIELD_CLASS}
            inputMode="numeric"
            value={termMonths}
            onChange={(event) => setTermMonths(event.target.value)}
            placeholder={fixedTerm ? "72" : ""}
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Started on
          <input
            className={FIELD_CLASS}
            type="date"
            required
            value={startedOn}
            onChange={(event) => setStartedOn(event.target.value)}
          />
        </label>

        {createDebt.isError ? (
          <p className="text-body text-signal-critical">
            Could not add the debt: {(createDebt.error as Error).message}
          </p>
        ) : null}

        <Button type="submit" disabled={createDebt.isPending}>
          {createDebt.isPending ? "Adding…" : "Add debt"}
        </Button>
      </form>
    </Card>
  );
}
