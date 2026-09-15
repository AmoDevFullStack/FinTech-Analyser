import { Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useCreateAccount } from "@/api/accounts";
import type { AccountType } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

import { ACCOUNT_TYPE_META, ACCOUNT_TYPES, CREDIT_LIMIT_TYPES, INTEREST_BEARING_TYPES } from "./accountAppearance";

const FIELD_CLASSES =
  "h-11 rounded-md border border-rule bg-surface-raised px-3 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

function emptyState() {
  return {
    name: "",
    accountType: "transactional" as AccountType,
    institution: "",
    openingBalance: "0.00",
    openedOn: "",
    interestRate: "",
    creditLimit: "",
  };
}

export function CreateAccountForm({ onCreated }: { onCreated?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState(emptyState);
  const create = useCreateAccount();

  const showInterestRate = INTEREST_BEARING_TYPES.includes(form.accountType);
  const showCreditLimit = CREDIT_LIMIT_TYPES.includes(form.accountType);

  function handleCancel() {
    setForm(emptyState());
    setExpanded(false);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      {
        name: form.name,
        account_type: form.accountType,
        institution: form.institution || undefined,
        opening_balance: form.openingBalance,
        opened_on: form.openedOn || undefined,
        interest_rate: showInterestRate && form.interestRate ? form.interestRate : undefined,
        credit_limit: showCreditLimit && form.creditLimit ? form.creditLimit : undefined,
      },
      {
        onSuccess: () => {
          setForm(emptyState());
          setExpanded(false);
          onCreated?.();
        },
      },
    );
  }

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex h-14 items-center justify-center gap-2 rounded-lg border border-dashed border-rule-meaning text-label font-medium text-content-secondary transition-colors duration-150 hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <Plus size={18} strokeWidth={2} aria-hidden="true" />
        Add account
      </button>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <span className="text-title">New account</span>
        <button
          type="button"
          aria-label="Cancel adding account"
          onClick={handleCancel}
          className="flex h-11 w-11 items-center justify-center rounded-full text-content-secondary hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <X size={18} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Account type">
          {ACCOUNT_TYPES.map((type) => {
            const meta = ACCOUNT_TYPE_META[type];
            const Icon = meta.icon;
            const selected = form.accountType === type;
            return (
              <button
                key={type}
                type="button"
                aria-pressed={selected}
                onClick={() => setForm((f) => ({ ...f, accountType: type }))}
                className={`flex h-11 items-center gap-2 rounded-full border px-3 text-label font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  selected
                    ? "border-accent bg-surface-sunken text-accent"
                    : "border-rule text-content-secondary hover:border-rule-meaning"
                }`}
              >
                <Icon size={16} strokeWidth={2} aria-hidden="true" />
                {meta.label}
              </button>
            );
          })}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Name</span>
            <input
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className={FIELD_CLASSES}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Institution</span>
            <input
              value={form.institution}
              onChange={(e) => setForm((f) => ({ ...f, institution: e.target.value }))}
              className={FIELD_CLASSES}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Opening balance</span>
            <input
              inputMode="decimal"
              value={form.openingBalance}
              onChange={(e) => setForm((f) => ({ ...f, openingBalance: e.target.value }))}
              className={FIELD_CLASSES}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Opened on</span>
            <input
              type="date"
              value={form.openedOn}
              onChange={(e) => setForm((f) => ({ ...f, openedOn: e.target.value }))}
              className={FIELD_CLASSES}
            />
          </label>
          {showInterestRate ? (
            <label className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Interest rate</span>
              <input
                inputMode="decimal"
                placeholder="0.0"
                value={form.interestRate}
                onChange={(e) => setForm((f) => ({ ...f, interestRate: e.target.value }))}
                className={FIELD_CLASSES}
              />
            </label>
          ) : null}
          {showCreditLimit ? (
            <label className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Credit limit</span>
              <input
                inputMode="decimal"
                value={form.creditLimit}
                onChange={(e) => setForm((f) => ({ ...f, creditLimit: e.target.value }))}
                className={FIELD_CLASSES}
              />
            </label>
          ) : null}
        </div>

        <div className="flex justify-end gap-3">
          <Button type="button" onClick={handleCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" icon={Plus} disabled={create.isPending}>
            Add account
          </Button>
        </div>
      </form>
    </Card>
  );
}
