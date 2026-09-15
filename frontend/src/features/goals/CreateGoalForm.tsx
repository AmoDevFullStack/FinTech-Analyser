import { useState } from "react";

import { useAccounts } from "@/api/accounts";
import { useCreateGoal } from "@/api/goals";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

const FIELD_CLASS =
  "rounded border border-rule bg-surface px-3 py-2 text-body text-content focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent";

export function CreateGoalForm() {
  const createGoal = useCreateGoal();
  const { data: accounts } = useAccounts();
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [priority, setPriority] = useState("1");
  const [accountId, setAccountId] = useState("");

  return (
    <Card>
      <h2 className="text-title">Add a goal</h2>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          createGoal.mutate(
            {
              name,
              target_amount: targetAmount,
              target_date: targetDate,
              priority,
              account_id: accountId || undefined,
            },
            {
              onSuccess: () => {
                setName("");
                setTargetAmount("");
                setTargetDate("");
                setPriority("1");
                setAccountId("");
              },
            },
          );
        }}
      >
        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Name
          <input
            className={FIELD_CLASS}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Emergency fund"
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Target amount
          <input
            className={FIELD_CLASS}
            inputMode="decimal"
            required
            value={targetAmount}
            onChange={(event) => setTargetAmount(event.target.value)}
            placeholder="90000.00"
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Target date
          <input
            className={FIELD_CLASS}
            type="date"
            required
            value={targetDate}
            onChange={(event) => setTargetDate(event.target.value)}
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Priority — 1 is funded first
          <input
            className={FIELD_CLASS}
            inputMode="numeric"
            required
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
          />
        </label>

        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Linked savings account — progress is then evidenced by its balance
          <select
            className={FIELD_CLASS}
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">No linked account</option>
            {(accounts ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>

        {createGoal.isError ? (
          <p className="text-body text-signal-critical">
            Could not add the goal: {(createGoal.error as Error).message}
          </p>
        ) : null}

        <Button type="submit" disabled={createGoal.isPending}>
          {createGoal.isPending ? "Adding…" : "Add goal"}
        </Button>
      </form>
    </Card>
  );
}
