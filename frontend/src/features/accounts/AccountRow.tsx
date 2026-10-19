import { Archive, Check, Clock, Pencil, PencilLine, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { useArchiveAccount } from "@/api/accounts";
import type { Account } from "@/api/types";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { MoneyText } from "@/components/MoneyText";
import { asMoney, formatRateAsPercent, rateAsPercentWidth } from "@/lib/money";

import { ACCOUNT_TYPE_META } from "./accountAppearance";
import { EditAccountForm } from "./EditAccountForm";

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

export function AccountRow({ account }: { account: Account }) {
  const [editing, setEditing] = useState(false);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const archive = useArchiveAccount();
  const meta = ACCOUNT_TYPE_META[account.account_type];
  const Icon = meta.icon;

  return (
    <Card>
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-content-secondary">
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
          </span>
          <div className="flex min-w-0 flex-col gap-1">
            <span className="truncate text-body font-medium">{account.name}</span>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-content-tertiary">
                {meta.label}
                {account.institution ? ` · ${account.institution}` : ""}
              </span>
              {account.balance_source === "manual" ? (
                <Chip icon={PencilLine}>Manual</Chip>
              ) : null}
              {account.is_manual_balance_stale ? <Chip icon={Clock}>Needs updating</Chip> : null}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <div className="mr-2 flex flex-col items-end gap-1">
            <MoneyText value={asMoney(account.current_balance)} />
            {account.credit_limit && account.utilisation ? (
              <span className="text-caption text-content-tertiary">
                {formatRateAsPercent(account.utilisation, { places: 0 })} of{" "}
                <MoneyText value={asMoney(account.credit_limit)} size="body" className="text-caption" />
              </span>
            ) : null}
          </div>
          {editing ? null : (
            <>
              <IconButton label={`Edit ${account.name}`} onClick={() => setEditing(true)}>
                <Pencil size={18} strokeWidth={2} aria-hidden="true" />
              </IconButton>
              {confirmingArchive ? (
                <>
                  <IconButton
                    label={`Confirm archiving ${account.name}`}
                    onClick={() => archive.mutate(account.id)}
                  >
                    <Check size={18} strokeWidth={2} aria-hidden="true" />
                  </IconButton>
                  <IconButton label="Cancel archiving" onClick={() => setConfirmingArchive(false)}>
                    <X size={18} strokeWidth={2} aria-hidden="true" />
                  </IconButton>
                </>
              ) : (
                <IconButton label={`Archive ${account.name}`} onClick={() => setConfirmingArchive(true)}>
                  <Archive size={18} strokeWidth={2} aria-hidden="true" />
                </IconButton>
              )}
            </>
          )}
        </div>
      </div>

      {account.credit_limit && account.utilisation ? (
        <div className="h-1.5 overflow-hidden rounded-full bg-surface-sunken" role="presentation">
          <div
            className="h-full rounded-full bg-content-tertiary"
            style={{ width: `${rateAsPercentWidth(account.utilisation)}%` }}
          />
        </div>
      ) : null}

      {editing ? (
        <EditAccountForm account={account} onDone={() => setEditing(false)} />
      ) : null}
    </Card>
  );
}
