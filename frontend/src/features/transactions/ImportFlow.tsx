import { Upload } from "lucide-react";
import { useState } from "react";

import { useAccounts } from "@/api/accounts";
import { ApiError } from "@/api/client";
import { useCommitImport, useUploadImport } from "@/api/transactions";
import { Button } from "@/components/Button";

/** Upload -> stage -> commit. Conflict resolution (specs/transactions.md step 3's
 * probable-duplicate surfacing) is a Next-phase UI addition — this "Now" slice covers
 * the golden path: a clean file with no conflicts, staged then committed in one flow.
 */
export function ImportFlow() {
  const { data: accounts } = useAccounts();
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const upload = useUploadImport();
  const commit = useCommitImport();

  function handleUpload() {
    if (!accountId || !file) return;
    upload.mutate(
      { accountId, file },
      {
        onSuccess: (summary) => {
          if (summary.rows_pending_conflict === 0) {
            commit.mutate(summary.batch_id);
          }
        },
      },
    );
  }

  const pendingConflict = upload.data?.rows_pending_conflict ?? 0;
  const result = commit.data ?? upload.data;
  const error = upload.error ?? commit.error;

  return (
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
        <span className="text-label text-content-secondary">CSV file</span>
        <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <Button
        variant="primary"
        icon={Upload}
        onClick={handleUpload}
        disabled={!accountId || !file || upload.isPending || commit.isPending}
      >
        {upload.isPending || commit.isPending ? "Importing…" : "Import"}
      </Button>
      {error ? (
        <p className="text-caption text-signal-critical">
          {error instanceof ApiError ? error.message : "Import failed."}
        </p>
      ) : result ? (
        <p className="text-caption text-content-tertiary">
          Parsed {result.rows_parsed}, imported {result.rows_imported}, skipped{" "}
          {result.rows_skipped_duplicate} exact duplicates
          {pendingConflict > 0 && !commit.data
            ? `, ${pendingConflict} awaiting conflict resolution (not yet imported).`
            : "."}
        </p>
      ) : null}
    </div>
  );
}
