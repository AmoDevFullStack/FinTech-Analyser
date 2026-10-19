import { Check, Upload } from "lucide-react";
import { useState } from "react";

import { useAccounts } from "@/api/accounts";
import { ApiError } from "@/api/client";
import { useCommitImport, useUploadImport, type ImportSummary } from "@/api/transactions";
import { Button } from "@/components/Button";

import { ImpactSummary } from "./ImpactSummary";

/**
 * Upload -> stage -> review -> commit.
 *
 * The review step is not optional and the flow no longer commits a clean file on its own.
 * specs/transactions.md is explicit that nothing reaches the transactions table until the
 * user commits, and the reason is the one the spec opens with: a duplicated salary makes
 * someone look R52,000 richer than they are, and every figure derived from it is wrong in
 * a way that looks plausible. Auto-committing whenever no conflict was detected meant the
 * only file a user got to inspect was one the system had already found a problem in.
 *
 * What is shown at that step is the detection and impact report from
 * backend/app/services/spending_insight.py: what each payment was for, what type of
 * payment it was, and what committing would do to the month.
 *
 * Conflict resolution (specs/transactions.md step 3's probable-duplicate surfacing) is
 * still a Next-phase UI addition; a file with conflicts stops here and says so.
 */
export function ImportFlow() {
  const { data: accounts } = useAccounts();
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [staged, setStaged] = useState<ImportSummary | null>(null);
  const upload = useUploadImport();
  const commit = useCommitImport();

  function handleUpload() {
    if (!accountId || !file) return;
    commit.reset();
    upload.mutate({ accountId, file, password: password || undefined }, { onSuccess: setStaged });
  }

  function handleReset() {
    setStaged(null);
    setFile(null);
    setPassword("");
    upload.reset();
    commit.reset();
  }

  const error = upload.error ?? commit.error;
  // The password field appears only once the server has said the file needs one. Asking
  // everybody for a password they usually do not have is a worse default than asking the
  // one person who does, at the moment it is known to matter.
  const needsPassword =
    upload.error instanceof ApiError &&
    Boolean((upload.error.details as { password_required?: boolean } | undefined)?.password_required);
  const committed = commit.data;
  const awaitingConflicts = (staged?.rows_pending_conflict ?? 0) > 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Account</span>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
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
          <span className="text-label text-content-secondary">Statement</span>
          <input
            type="file"
            accept=".csv,text/csv,.pdf,application/pdf"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setStaged(null);
              commit.reset();
            }}
          />
          <span className="text-caption text-content-tertiary">
            The PDF your bank sends, or a CSV export
          </span>
        </label>

        {needsPassword ? (
          <label className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Statement password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="off"
              className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
            />
            <span className="text-caption text-content-tertiary">
              Used to open this file and not stored
            </span>
          </label>
        ) : null}
        <Button
          variant="primary"
          icon={Upload}
          onClick={handleUpload}
          disabled={!accountId || !file || upload.isPending}
        >
          {upload.isPending ? "Reading…" : "Read file"}
        </Button>
        {error ? (
          <p className="text-caption text-signal-critical">
            {error instanceof ApiError ? error.message : "Import failed."}
          </p>
        ) : null}
      </div>

      {staged && !committed ? (
        <div className="flex flex-col gap-4">
          <p className="text-caption text-content-tertiary">
            Read {staged.rows_parsed} rows. {staged.rows_imported === 0 ? "None" : ""}{" "}
            {staged.rows_skipped_duplicate > 0
              ? `${staged.rows_skipped_duplicate} are exact duplicates and will be skipped. `
              : ""}
            Nothing has been saved yet.
          </p>

          {staged.insight ? (
            <ImpactSummary insight={staged.insight} heading="What this file would change" />
          ) : null}

          {awaitingConflicts ? (
            <p className="text-body text-signal-caution">
              {staged.rows_pending_conflict} row
              {staged.rows_pending_conflict === 1 ? "" : "s"} could be a duplicate of a
              transaction already recorded. Resolving those is not yet possible here, and
              the file cannot be imported until it is.
            </p>
          ) : (
            <div className="flex items-center gap-3">
              <Button
                variant="primary"
                icon={Check}
                onClick={() => commit.mutate(staged.batch_id)}
                disabled={commit.isPending}
              >
                {commit.isPending ? "Importing…" : "Import these transactions"}
              </Button>
              <Button type="button" onClick={handleReset}>
                Discard
              </Button>
            </div>
          )}
        </div>
      ) : null}

      {committed ? (
        <div className="flex flex-col gap-4">
          <p className="text-caption text-content-tertiary">
            Imported {committed.rows_imported} transactions, skipped{" "}
            {committed.rows_skipped_duplicate} exact duplicates
            {committed.rows_merged > 0 ? `, merged ${committed.rows_merged}` : ""}.
          </p>
          {committed.insight ? (
            <ImpactSummary insight={committed.insight} heading="What this import changed" />
          ) : null}
          <div>
            <Button type="button" onClick={handleReset}>
              Import another file
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
