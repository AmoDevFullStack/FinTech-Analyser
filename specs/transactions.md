# Transactions

## Objective

Get a user's real financial history into the system accurately, with no duplicates and no
silent corruption, because every projection downstream is built on it.

This is the least glamorous feature and the one most likely to destroy trust. A duplicated
salary makes the user look R52,000 richer than they are, and every figure derived from it
is wrong in a way that looks plausible.

## Inputs

CSV export from a South African bank — FNB, Standard Bank, Absa, Nedbank, Capitec,
Discovery, TymeBank. Manual entry for a single transaction. Adjustment entries created by
the user to correct a derived balance.

## Processing

### 1. Format detection

Detect the institution from the header row and column shapes. Where detection fails, the
user maps columns manually and the mapping is remembered for that account.

Parse into a staging table. Nothing reaches the transactions table until the user commits.

### 2. Normalisation

Strip institution noise from descriptions — reference numbers, terminal identifiers, card
suffixes, dates repeated in the text — into `normalised_description`. The original is
retained unchanged, because the user recognises their own statement text.

Apply the sign convention from `docs/database.md`: outflows negative, inflows positive, for
every account type without exception.

### 3. Deduplication

Two passes, following reconciliation practice.

**Exact.** Fingerprint over user, account, date, amount, and normalised description.
A fingerprint collision with a non-deleted row is a certain duplicate and is skipped
silently, with a count reported.

**Probable.** Same amount within a ±3 day window with a description similarity above
threshold. These are surfaced to the user as conflicts with both rows shown side by side,
and are never auto-resolved. The user chooses import, skip, or merge.

Rationale: the same transaction legitimately arrives twice from a re-export with a shifted
posting date, and a genuine duplicate charge also exists. Only the user can distinguish
them, and guessing wrong in either direction is worse than asking.

### 4. Transfer detection

An outflow on one of the user's accounts matching an inflow on another — same amount,
within 3 days, opposite sign — is a transfer. Both legs share a `transfer_group_id` and are
excluded from income and expenditure totals.

Missing this inflates both income and spending by the transferred amount and corrupts
savings rate, cash flow, and the health score simultaneously.

### 5. Categorisation

Rules first, then similarity against the user's own corrected history, then a default
category with low confidence. Confidence is stored.

A user correction sets `category_set_by_user` and is never overwritten by a later automatic
pass. Corrections also become training signal for that user's future categorisation.

### 6. Recurrence detection

Identify series: same normalised description, similar amount, regular interval across at
least three occurrences. Assign a `recurrence_group_id` and a frequency.

Recurring commitments and discretionary spending behave differently under projection. A
R900 monthly debit order continues; a R900 restaurant bill may not.

### 7. Commit

Write staged rows in one transaction. Record an import batch so the whole import can be
undone until a subsequent import commits.

Invalidate derived balances and mark forecasts stale for affected accounts.

## Output

Import summary: rows parsed, imported, skipped as exact duplicates, pending conflict
resolution, uncategorised. Transaction list with filters and search. Recurring series view.

## Constraints

- Nothing reaches the transactions table before commit.
- Probable duplicates are never auto-resolved.
- A user's category correction is never silently overwritten.
- Transfers never count as income or expenditure.
- Import is idempotent: the same file imported twice produces no new rows.
- A failed import leaves no partial state.

## Acceptance criteria

- [ ] Each supported bank's CSV format parses without manual mapping.
- [ ] Unknown formats fall back to manual column mapping, remembered per account.
- [ ] Re-importing an identical file imports zero rows.
- [ ] Near-duplicates surface as conflicts and await a decision.
- [ ] Both legs of an internal transfer are detected and excluded from totals.
- [ ] User category corrections survive subsequent automatic categorisation.
- [ ] Recurring series are detected from three or more occurrences.
- [ ] Undo removes exactly the rows a batch added.
- [ ] A 10,000-row file imports without timeout.
- [ ] Affected balances recompute and affected forecasts are marked stale.
