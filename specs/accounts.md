# Accounts

## Objective

Give the user a complete picture of where their money sits, including accounts the system
cannot see transactions for, without presenting guessed balances and known balances as
equally reliable.

## Inputs

Account creation accepts name, type, institution, opening balance, opened date, and — for
interest-bearing or credit accounts — rate and limit.

Supported types: transactional, savings, credit card, loan, home loan, vehicle finance,
investment, manual asset.

## Processing

**Balance derivation.** Where an account has transactions, its balance is derived: opening
balance plus the sum of transactions to date. Where it has none, the balance is whatever
the user entered. The account records which of the two applies.

A derived balance is recomputed whenever transactions for that account change. It is never
maintained incrementally, because an incrementally maintained balance drifts and drift here
is indistinguishable from an engine bug.

**Manual balance ageing.** A manually entered balance carries the date it was entered.
After 30 days it is shown with its age. After 90 days the system prompts for an update and
treats it as low-confidence input to net worth.

**Credit accounts.** Balance is the amount owed, stored negative. Available credit is limit
minus balance owed. Utilisation is balance owed over limit, and feeds financial health.

**Archival.** Archiving hides an account from the active list and excludes it from current
position, while retaining its transactions for historical analysis. A closed credit card
still explains last year's spending.

## Output

Account list with balance, source, and — for credit — limit and utilisation. Balance
history series for charting. Aggregate position contributions grouped by type.

## Constraints

- An account belongs to exactly one user and is never visible to another.
- Deleting an account with transactions soft deletes it; transactions are retained.
- A derived balance is never overwritten by a manual entry. To correct a derived balance
  the user corrects the transactions, or adds an explicit adjustment transaction.
- Archived accounts are excluded from current position and included in historical analysis.

## Acceptance criteria

- [ ] User can create an account of each supported type.
- [ ] Balance is derived where transactions exist and manual where they do not.
- [ ] The API exposes which of the two applies, and the UI renders the distinction.
- [ ] A manual balance older than 90 days is flagged.
- [ ] Credit utilisation is computed and exposed.
- [ ] Archiving preserves history and removes the account from current position.
- [ ] Soft delete retains transactions.
- [ ] Repository tests prove no query returns another user's accounts.
