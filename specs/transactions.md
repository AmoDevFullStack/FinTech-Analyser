# Transactions

## Objective

Get a user's real financial history into the system accurately, with no duplicates and no
silent corruption, because every projection downstream is built on it.

This is the least glamorous feature and the one most likely to destroy trust. A duplicated
salary makes the user look R52,000 richer than they are, and every figure derived from it
is wrong in a way that looks plausible.

## Inputs

Statement **PDF** or **CSV export** from a South African bank — FNB, Standard Bank, Absa,
Nedbank, Capitec, Discovery, TymeBank. Manual entry for a single transaction. Adjustment
entries created by the user to correct a derived balance.

The PDF is the form most statements actually arrive in; the CSV export is the one a user has
to go looking for. Both end at the same staging table and go through the same pipeline.

## Processing

### 1. Format detection

**CSV.** Detect the institution from the header row and column shapes. Where detection
fails, the user maps columns manually and the mapping is remembered for that account.

**PDF.** Read the text layer — never OCR, and never a language model, which ADR-002 forbids
from producing any financial value. A transaction line is one that starts with a date and
ends with a money figure; everything else is skipped by that rule rather than by a list of
things to ignore.

Two things a PDF gives that a CSV does not, and both are used:

- **The running balance decides the sign.** Where a balance column is present, an amount is
  `balance(n) - balance(n - 1)`, not the sign printed beside it. Statements write a debit
  four different ways, and a debit read as a credit inflates income by the amount spent —
  precisely the silent corruption this spec opens by naming.
- **The statement checks its own parse.** Opening plus everything read must equal closing,
  and no line's printed amount may contradict its own balance movement. A statement that
  fails either is refused with what did not add up, never partially imported.

  The second check is the one that catches a missed line. Amounts derived from balance
  movements always sum to the closing balance, so dropping a line opens no gap — the next
  line absorbs it. The absorbing line's printed amount is what no longer matches.

A protected PDF is opened with a password supplied on upload and never stored. A PDF with no
text layer — a scan, a photograph — is refused: a digit guessed out of an image has no
business behind a financial figure.

Parse into a staging table. Nothing reaches the transactions table until the user commits.

### 2. Normalisation

Strip institution noise from descriptions — reference numbers, terminal identifiers, card
suffixes, dates repeated in the text — into `normalised_description`. The original is
retained unchanged, because the user recognises their own statement text.

Apply the sign convention from `docs/database.md`: outflows negative, inflows positive, for
every account type without exception.

### 2a. Spending detection

Read two independent facts off each line and store both: the **payment method** (how the
money moved — a debit order, a card swipe, an ATM withdrawal, an EFT) and the **spending
purpose** (what it was for — rent, groceries, a medical aid premium, a loan instalment).
The counterparty is extracted alongside them as `merchant`.

They are separate because they answer different questions and are wrong independently.
The method is the strongest available evidence about whether a payment will happen again:
a debit order is a contract, a card purchase is a decision. The purpose is what decides
whether the money was essential, discretionary, debt service, saving, or income, and
therefore what every cash-flow figure downstream says. "DEBIT ORDER: DISCOVERY LIFE" and
"CARD PURCHASE: DISCOVERY STORE" share a merchant token and are not the same kind of
spending.

Rent has explicit coverage, as do bond repayments, levies, municipal rates, utilities,
vehicle finance, insurance, medical aid, school fees, and domestic help. Rent is the
largest monthly commitment for a large share of users, it is essential rather than
discretionary, and a system that cannot name it produces a cash-flow picture that is wrong
by the size of someone's rent. Rent and a bond instalment are separate purposes with
different kinds: both are the roof over someone's head, but only one is a debt the payoff
engines can schedule.

Detection runs at staging, not at commit, so the impact preview a user approves is
computed from the same classification the committed rows carry.

An unrecognised line resolves to `unknown` and is counted as needing review. It is never
resolved to a plausible guess: a wrong purpose silently moves a figure the user will act
on, while an unknown one shows up as uncategorised and gets looked at.

### 3. Deduplication

Two passes, following reconciliation practice.

**Exact.** Fingerprint over user, account, date, amount, and normalised description.
A fingerprint collision with a non-deleted row is a certain duplicate and is skipped
silently, with a count reported.

**Probable.** Same amount within a ±3 day window with a description similarity above
threshold. Similarity is token-aware Levenshtein distance (`app/domain/text_match.py`),
the same measure used by categorisation and by search, so one threshold means the same
thing everywhere it is applied. These are surfaced to the user as conflicts with both rows shown side by side,
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

Rules first, then similarity against the user's own corrected history, then the detected
spending purpose, then a default category with low confidence. Confidence is stored.

In full: an explicit rule (a category whose name appears as a whole word in the
description), then an exact correction, then a correction within edit distance, then the
purpose from step 2a, then the discretionary fallback.

The purpose sits below the user's own corrections deliberately. The taxonomy is a shipped
generalisation about what a merchant sells; a correction is this user saying what this
payment was, and where they disagree the user is right about their own money. It sits
above the default because "we recognised this as a rent debit order" is a real finding,
and filing it as discretionary spending would be a lie of omission.

Rule matching is on whole words. "Rent" inside "current account fee" is not a rent
payment, and with a seeded chart of accounts a substring test files every monthly account
fee as the largest line in the budget.

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

Before the commit, report what committing would do: the cash-flow effect and the effect on
every figure derived from it — surplus, cash-flow margin, savings rate, debt-to-income, and
emergency-fund cover — as monthly averages over the calendar months the file spans, on both
sides of the comparison. A six-month statement adds six months of rent, and charging all of
it to one month would report a collapse that did not happen.

Emergency-fund cover moves on an import even when no savings balance changed, because
essential spending is its denominator. Report it rather than leaving the user to discover
it on the dashboard afterwards.

Name what else the commit changes, rather than leaving it implied: the account's derived
balance, the position snapshot, the health assessment, the forecast's staleness, and
recurring-series detection. Each of those is a figure the user has seen and may be about to
act on.

Standing commitments the file introduces are reported separately from detected series. A
debit order is a standing arrangement on its first appearance, while step 6 needs three
occurrences before it will call something a series — both are true, and a preview that
cannot say "this file adds a R14,500 monthly commitment" until the third month of
statements is withholding the most important thing in the file.

## Output

Import summary: rows parsed, imported, skipped as exact duplicates, pending conflict
resolution, uncategorised. Per-row payment method, spending purpose, and merchant, with
totals by each. The before/after impact report described in step 7. Transaction list with
filters and search. Recurring series view.

Search matches descriptions by edit distance as well as by substring. A user typing a
merchant name means "find this merchant", and the statement spells that merchant three
different ways — a search that only finds what the user can spell exactly as their bank
prints it finds one of the three. A fuzzy result is labelled as one; "contains what you
typed" and "looks like what you typed" are different claims.

## Constraints

- Nothing reaches the transactions table before commit, and the commit is the user's
  decision on every file — not only on files a conflict was found in.
- Probable duplicates are never auto-resolved.
- An unrecognised payment is reported as unrecognised, never as a plausible guess.
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
- [ ] A rent debit order is detected as rent, as essential, and as a standing commitment on
      its first appearance.
- [ ] A misspelled merchant is found by search and categorised as that merchant.
- [ ] The impact report shown before a commit matches the one shown after it.
- [ ] Undo removes exactly the rows a batch added.
- [ ] A 10,000-row file imports without timeout.
- [ ] Affected balances recompute and affected forecasts are marked stale.
