import { ArrowUpRight, Check, Pencil, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useDeleteDebt } from "@/api/debts";
import type { Debt } from "@/api/types";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { asMoney, formatRateAsPercent } from "@/lib/money";

import { DEBT_TYPE_LABELS } from "./debtAppearance";
import { EditDebtForm } from "./EditDebtForm";

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex h-11 w-11 items-center justify-center rounded-full text-content-secondary transition-colors duration-150 hover:bg-surface-sunken hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      {children}
    </button>
  );
}

/**
 * One debt, editable in place.
 *
 * The row itself opens the editor on click, which is what makes the list feel like the
 * thing rather than a read-only report of it. Two things follow from that and are easy to
 * get wrong:
 *
 *   * The row is a `<button>`, not a `<div>` with an onClick. A clickable div is invisible
 *     to the keyboard and to a screen reader, and this is the only way to edit a debt.
 *   * The "open the detail page" affordance stays a real `<Link>` beside it rather than
 *     being nested inside the button — a link inside a button is invalid HTML and browsers
 *     resolve it by ignoring one of them, unpredictably.
 *
 * Deleting asks first, inline, following AccountRow's archive confirmation. A debt carries
 * a payoff schedule and a strategy comparison built on it, and removing it silently on a
 * misclick is not recoverable from this screen.
 */
export function DebtRow({ debt }: { debt: Debt }) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const remove = useDeleteDebt();
  const label = DEBT_TYPE_LABELS[debt.debt_type];

  return (
    <li className="flex flex-col gap-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-expanded={editing}
          aria-label={`Edit ${label}`}
          onClick={() => setEditing((open) => !open)}
          className="flex min-w-0 flex-1 flex-col items-start gap-0.5 rounded-md px-2 py-1 text-left transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <span className="text-body">{label}</span>
          <span className="text-caption text-content-tertiary">
            {formatRateAsPercent(debt.annual_rate, { places: 2 })} · minimum{" "}
            <MoneyText value={asMoney(debt.minimum_payment)} size="body" /> · since{" "}
            {formatDate(debt.started_on)}
          </span>
        </button>

        <div className="flex shrink-0 items-center gap-1">
          <MoneyText value={asMoney(debt.current_balance)} />
          <Link
            to={`/debts/${debt.id}`}
            aria-label={`Open the ${label} schedule`}
            className="flex h-11 w-11 items-center justify-center rounded-full text-content-secondary transition-colors duration-150 hover:bg-surface-sunken hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <ArrowUpRight size={18} strokeWidth={2} aria-hidden="true" />
          </Link>
          {editing ? null : (
            <IconButton label={`Edit ${label}`} onClick={() => setEditing(true)}>
              <Pencil size={18} strokeWidth={2} aria-hidden="true" />
            </IconButton>
          )}
          {confirmingDelete ? (
            <>
              <IconButton
                label={`Confirm removing ${label}`}
                onClick={() => remove.mutate(debt.id)}
              >
                <Check size={18} strokeWidth={2} aria-hidden="true" />
              </IconButton>
              <IconButton label="Cancel removing" onClick={() => setConfirmingDelete(false)}>
                <X size={18} strokeWidth={2} aria-hidden="true" />
              </IconButton>
            </>
          ) : (
            <IconButton label={`Remove ${label}`} onClick={() => setConfirmingDelete(true)}>
              <Trash2 size={18} strokeWidth={2} aria-hidden="true" />
            </IconButton>
          )}
        </div>
      </div>

      {confirmingDelete ? (
        <p className="px-2 text-caption text-content-secondary">
          Removing this debt takes its instalment out of every projection and out of the
          payoff strategy comparison. Its transactions stay.
        </p>
      ) : null}

      {remove.isError ? (
        <p className="px-2 text-caption text-signal-critical">
          Could not remove the debt: {(remove.error as Error).message}
        </p>
      ) : null}

      {editing ? <EditDebtForm debt={debt} onDone={() => setEditing(false)} /> : null}
    </li>
  );
}
