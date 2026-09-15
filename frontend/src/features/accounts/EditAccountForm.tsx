import { useState, type FormEvent } from "react";

import { useUpdateAccount } from "@/api/accounts";
import type { Account } from "@/api/types";
import { Button } from "@/components/Button";

import { CREDIT_LIMIT_TYPES, INTEREST_BEARING_TYPES } from "./accountAppearance";

const FIELD_CLASSES =
  "h-11 rounded-md border border-rule bg-surface-raised px-3 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export function EditAccountForm({ account, onDone }: { account: Account; onDone: () => void }) {
  const [name, setName] = useState(account.name);
  const [institution, setInstitution] = useState(account.institution ?? "");
  const [openedOn, setOpenedOn] = useState(account.opened_on ?? "");
  const [interestRate, setInterestRate] = useState(account.interest_rate ?? "");
  const [creditLimit, setCreditLimit] = useState(account.credit_limit ?? "");
  const [balance, setBalance] = useState<string>(account.current_balance);
  const update = useUpdateAccount();

  const showInterestRate = INTEREST_BEARING_TYPES.includes(account.account_type);
  const showCreditLimit = CREDIT_LIMIT_TYPES.includes(account.account_type);
  const balanceIsEditable = account.balance_source === "manual";

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        accountId: account.id,
        data: {
          name,
          institution: institution || undefined,
          opened_on: openedOn || undefined,
          interest_rate: showInterestRate && interestRate ? interestRate : undefined,
          credit_limit: showCreditLimit && creditLimit ? creditLimit : undefined,
          balance: balanceIsEditable && balance ? balance : undefined,
        },
      },
      { onSuccess: onDone },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 border-t border-rule pt-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Name</span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={FIELD_CLASSES}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Institution</span>
          <input
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            className={FIELD_CLASSES}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Opened on</span>
          <input
            type="date"
            value={openedOn}
            onChange={(e) => setOpenedOn(e.target.value)}
            className={FIELD_CLASSES}
          />
        </label>
        {balanceIsEditable ? (
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Current balance</span>
            <input
              inputMode="decimal"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className={FIELD_CLASSES}
            />
          </label>
        ) : (
          <div className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Current balance</span>
            <p className="flex h-11 items-center text-caption text-content-tertiary">
              Calculated from transactions — correct a transaction to change it.
            </p>
          </div>
        )}
        {showInterestRate ? (
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Interest rate</span>
            <input
              inputMode="decimal"
              value={interestRate}
              onChange={(e) => setInterestRate(e.target.value)}
              className={FIELD_CLASSES}
            />
          </label>
        ) : null}
        {showCreditLimit ? (
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Credit limit</span>
            <input
              inputMode="decimal"
              value={creditLimit}
              onChange={(e) => setCreditLimit(e.target.value)}
              className={FIELD_CLASSES}
            />
          </label>
        ) : null}
      </div>

      {update.isError ? (
        <p className="text-caption text-signal-critical">{update.error.message}</p>
      ) : null}

      <div className="flex justify-end gap-3">
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          Save changes
        </Button>
      </div>
    </form>
  );
}
