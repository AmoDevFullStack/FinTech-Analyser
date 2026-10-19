# API specification

Base URL: `/api/v1`

This file is the contract. Code follows it, not the other way round. Contract tests assert
that responses match what is written here — if you change an endpoint, change this file in
the same pull request or the tests will fail, which is the intended behaviour.

---

## Conventions

**Authentication** is either a session cookie (`HttpOnly`, `Secure`, `SameSite=Lax`) or a
JWT bearer token, and a request that carries both is answered as the bearer token's user.
Every endpoint except `/auth/register`, `/auth/login`, `/auth/refresh`, and `/health`
requires one of them. See the Authentication section below for which to use.

**Money is a string.** `"4312.67"`, never `4312.67`. JSON numbers are IEEE 754 doubles and
would defeat ADR-001 at the last step. Clients parse for display and never for arithmetic.

**Dates** are `YYYY-MM-DD`. **Timestamps** are RFC 3339 with offset.

**Identifiers** are UUIDs.

**Pagination** is cursor-based on list endpoints: `?limit=50&cursor=<opaque>`. Responses
carry `{"data": [...], "next_cursor": "..." | null}`. Offset pagination is not used —
transaction lists change under the reader.

**Projected values** carry `generated_at` and `is_stale` wherever they appear, per ADR-003.
A client that renders a projection without its generation date is a client bug.

**Errors** use one envelope throughout:

```json
{
  "error": {
    "code": "scenario_not_found",
    "message": "No scenario with that identifier exists for this user.",
    "details": {}
  }
}
```

Status codes: 400 validation, 401 unauthenticated, 403 unauthorised, 404 not found, 409
conflict, 422 semantically invalid but well-formed, 429 rate limited, 500 unexpected.

A request for a resource belonging to another user returns 404, not 403. Distinguishing
the two leaks the existence of records.

**Idempotency**: `POST` endpoints that create financial state accept an
`Idempotency-Key` header. Replays return the original response.

---

## Authentication

```
POST   /auth/register        {email, password, full_name}
POST   /auth/login           {email, password}
POST   /auth/refresh         {refresh_token}
POST   /auth/logout          {refresh_token?}
GET    /auth/me
GET    /auth/verify
POST   /auth/password-reset          {email}
POST   /auth/password-reset/confirm  {token, password}
POST   /auth/mfa/enroll
POST   /auth/mfa/verify              {code}
```

### Two credentials

`register` and `login` set the session cookie **and** return a JWT pair:

```json
{
  "id": "0192f0c1-...",
  "email": "nadia@example.com",
  "full_name": "Nadia",
  "currency": "ZAR",
  "timezone": "Africa/Johannesburg",
  "tokens": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "token_type": "Bearer",
    "expires_in": 900
  }
}
```

A client uses whichever suits it and ignores the other. A browser on the same origin is
fine with the cookie; anything that cannot hold one sends
`Authorization: Bearer <access_token>`.

Where a request carries both, the bearer token wins. A request that troubles to send an
`Authorization` header means that identity, and answering as whoever a stale cookie names
would be a cross-user data leak in a system where every query is scoped by user id.

### Token lifetimes and revocation

| | Access | Refresh |
|---|---|---|
| Life | 15 minutes (`JWT_ACCESS_TTL_SECONDS`) | 30 days (`JWT_REFRESH_TTL_SECONDS`) |
| Sent to | every endpoint | `POST /auth/refresh` only |
| Revocable | no | yes |

The access token is **not** checked against the revocation list. Doing so would put a Redis
round trip in front of every API call to close a window that is already only fifteen
minutes wide; its short life is the revocation mechanism.

`POST /auth/refresh` **rotates**: the token presented is revoked as the new pair is issued,
so a refresh token works exactly once. A stolen refresh token that an attacker uses
therefore breaks the real user's next refresh — a visible failure rather than a silent
parallel session. It is reachable without authentication, because its whole purpose is to
work once the access token has expired.

`POST /auth/logout` clears the cookie and, when a `refresh_token` is supplied in the body,
revokes it. The token is supplied rather than inferred: the request is authenticated with
the *access* token, and the server cannot tell which of a user's refresh tokens belongs to
this session. A logout without one still succeeds and still clears the cookie.

A 401 distinguishes its causes — `"The token has expired."` means refresh, `"The token is
not valid."` means log in again, `"The token has been revoked."` means this session is
over. The distinction tells a client what to do and tells an attacker nothing they could
not learn by waiting.

`GET /auth/me` returns the user without financial data. Position comes from
`/position`, because identity and financial state are different concerns with different
cache behaviour. `GET /auth/verify` returns the same payload plus `expires_at`, so a client
holding only the token string can decide whether to refresh without decoding a JWT.

Login is rate limited to 5 attempts per 15 minutes per email and per IP. Failed login
returns 401 with a generic message regardless of whether the email exists.

---

## Position

```
GET    /position
GET    /position/history?from=&to=
POST   /position/snapshot
```

`GET /position` is the command centre payload — the single call the dashboard makes.

```json
{
  "as_of": "2026-09-14T06:00:00+02:00",
  "net_worth": "412500.00",
  "liquid_savings": "48200.00",
  "total_debt": "287300.00",
  "monthly_income": "52000.00",
  "monthly_essential": "31400.00",
  "monthly_discretionary": "9800.00",
  "projected_cash_flow": "10800.00",
  "emergency_fund_months": "1.53",
  "health_score": 62,
  "health_generated_at": "2026-09-14T06:00:00+02:00",
  "health_score_change": 4,
  "health_largest_negative_contributor": "emergency_cover",
  "upcoming_obligations": [
    {"label": "Vehicle finance", "amount": "6843.41", "due_on": "2026-09-25"}
  ],
  "active_risk_flags": 2,
  "is_stale": false
}
```

This endpoint reads stored results only. It must not trigger computation — see ADR-003 and
the 500ms target in `docs/requirements.md`.

`health_score_change` is this assessment's score minus the previous one (`null` with fewer
than two stored assessments). `health_largest_negative_contributor` names the component
dragging the score down most. Both exist so the dashboard's trend arrow and "largest
contributing factor" (specs/dashboard.md region 4) come from this one call, rather than a
second request to `GET /health-assessment`.

---

Monthly figures — `monthly_income`, `monthly_essential`, `monthly_discretionary`,
`projected_cash_flow` — are measured over the most recent month that has transactions, not
over the current calendar month. The payload says which, and how much history stands behind
it:

```json
{
  "baseline_month": "2026-07",
  "months_of_history": 3,
  "transactions_counted": 84,
  "last_transaction_on": "2026-07-24"
}
```

`baseline_month` is null and the counts are zero for a user with no transactions yet; the
monthly figures are then genuinely zero, which is "we have nothing to go on" rather than
"you earned nothing".

## Accounts

```
GET    /accounts?include_archived=false
POST   /accounts
GET    /accounts/{id}
PATCH  /accounts/{id}
POST   /accounts/{id}/archive
DELETE /accounts/{id}
GET    /accounts/{id}/balance-history?from=&to=
```

Account responses include `balance_source` so the client can distinguish a derived balance
from a manually entered one. `DELETE` soft deletes.

---

## Transactions

```
GET    /transactions
GET    /transactions/months            ?from&to&account_id
POST   /transactions                   {account_id, occurred_on, amount, description, category_id?}
POST   /transactions/classify          {description, amount}
POST   /transactions/reclassify
GET    /transactions/{id}
PATCH  /transactions/{id}
DELETE /transactions/{id}
POST   /transactions/bulk-categorise   {transaction_ids[], category_id}
```

### Listing and search

`GET /transactions` accepts:

| Parameter | Default | Notes |
|---|---|---|
| `account_id`, `category_id` | — | UUID |
| `from`, `to` | — | `YYYY-MM-DD`; `to` may not precede `from` |
| `min_amount`, `max_amount` | — | money strings |
| `direction` | — | `debit` or `credit` |
| `payment_method` | — | see the taxonomy below |
| `spending_purpose` | — | see the taxonomy below |
| `is_recurring` | — | boolean |
| `uncategorised_only` | `false` | rows with no category, for review |
| `q` | — | description search |
| `fuzzy` | `true` | also match descriptions within edit distance of `q` |
| `min_score` | `0.62` | similarity floor for a fuzzy match, 0-1 |
| `limit` | `50` | 1-500 |

An unknown parameter is a 400 with the offending name in `details.fields`, rather than a
filter that is silently not applied.

With `fuzzy` on — the default — `q` matches by Levenshtein distance as well as by
substring, so a search for `woolwrths` finds `POS PURCH 4471 WOOLWORTHS CLAREMONT`. Each
row carries how it matched:

```json
{
  "data": [{ "...": "...", "match_score": "0.904762", "match_basis": "fuzzy" }],
  "next_cursor": null,
  "search": { "q": "woolwrths", "fuzzy": true, "min_score": "0.62" }
}
```

`match_basis` is `exact` for a substring hit, `fuzzy` for an edit-distance one, and
`filter` when no search term was given. Exact hits score 1 and always sort first.

### Month by month

`GET /transactions/months` answers "how does this month compare with the last" over whole
calendar months. The list endpoint answers what happened; this answers how it changed.

| Parameter | Default | Notes |
|---|---|---|
| `from`, `to` | last 12 months | `YYYY-MM-DD`, widened to whole calendar months |
| `account_id` | every account | one account instead of all of them |

At most 60 months in one window.

```json
{
  "data": [
    {
      "month": "2026-07",
      "previous_month": "2026-06",
      "totals": {
        "income": "52000.00",
        "essential": "31400.00",
        "discretionary": "9800.00",
        "saving": "0.00",
        "debt_service": "0.00",
        "spending": "41200.00",
        "net": "10800.00"
      },
      "changes": {
        "essential": {
          "previous": "16900.00",
          "current": "31400.00",
          "change": "14500.00",
          "percentage_change": "0.857988"
        }
      },
      "cash": {
        "opening": "37400.00",
        "inflow": "52000.00",
        "outflow": "41200.00",
        "closing": "48200.00"
      },
      "transaction_count": 84,
      "import_batch_ids": ["0198e1c2-..."]
    }
  ],
  "months": 12
}
```

Things worth knowing about the shape:

- **`totals` excludes internal transfers; `cash` includes them.** They answer different
  questions. Moving R5,000 to a savings account is neither income nor spending, but it did
  leave the account it left, and a balance that ignores it will not reconcile to a
  statement.
- **`saving` counts inside `spending`.** A month that put R3,000 away had R3,000 less
  available. `net` is `income - spending`, and is negative in a month that overspent.
- **`percentage_change` is `null` when the previous month was zero.** From nothing to
  something has no percentage, and a `0` there would read as "unchanged".
- **`cash` is `null`** when nothing in scope holds a cash balance — a window over a credit
  card alone. The flows are still real.
- **`cash` is walked backwards** from what the accounts hold today, through every month
  since, so a window that ended in March is not dated by what happened in April.
- **`import_batch_ids`** are the uploads this month's rows came from, so a figure that
  moved can be traced to the statement that moved it. Empty for a month typed in by hand.
- The first month in the window is still compared against the month before it, which is
  read but not returned.

### Spending detection

Every transaction carries what the statement line said it was, independently of the
category it was filed under:

```json
{
  "payment_method": "debit_order",
  "spending_purpose": "rent",
  "merchant": "rent property group",
  "purpose_confidence": "0.900000"
}
```

`payment_method` is how the money moved — `debit_order`, `stop_order`, `card_purchase`,
`card_online`, `atm_withdrawal`, `cash_deposit`, `eft_out`, `eft_in`, `instant_payment`,
`internal_transfer`, `salary_deposit`, `cheque`, `bank_fee`, `interest`, `reversal`,
`unknown`.

`spending_purpose` is what it was for — `rent`, `bond_repayment`, `levies`,
`rates_and_taxes`, `utilities`, `groceries`, `fuel`, `transport`, `vehicle_instalment`,
`insurance`, `medical`, `telecoms`, `subscriptions`, `dining`, `entertainment`, `clothing`,
`education`, `childcare`, `domestic_help`, `savings`, `investment`, `debt_repayment`,
`bank_charges`, `salary`, `other_income`, `internal_transfer`, `unknown`.

The two are separate because they are decided by separate evidence and are wrong
independently: `DEBIT ORDER 4471992` is a certain method and an unknown purpose. All four
fields are `null` on a row imported before detection existed and never reclassified —
"not looked at" and "looked at and could not tell" are different claims.

`POST /transactions/classify` runs the rules without storing anything, for showing a user
what an entry will be filed as before they commit to it.
`POST /transactions/reclassify` re-runs detection over the caller's whole history. It is
explicit and user-initiated: re-running a changed rule table silently would move figures a
user has already seen with no record of why. Categories are untouched by it.

### Import

Import is a separate resource because it is a multi-step process with its own state:

```
POST   /imports                        multipart CSV upload
GET    /imports/{id}                   status, counts, detected format
GET    /imports/{id}/preview           detection and impact, before committing
GET    /imports/{id}/conflicts         probable duplicates awaiting decision
POST   /imports/{id}/resolve           {resolutions: [{candidate_id, action}]}
POST   /imports/{id}/commit
POST   /imports/{id}/undo
```

`POST /imports` returns 202 with a job identifier. Parsing and matching are asynchronous;
the client polls `GET /imports/{id}`.

Conflicts are surfaced rather than auto-resolved, per requirement 3. `action` is one of
`import`, `skip`, or `merge`.

`undo` is available until a subsequent import commits, and is recorded in the audit log.

`POST /imports` accepts a **statement PDF or a CSV**, decided from the file's leading bytes
rather than its name. Multipart fields: `account_id`, `file`, optional `mapping` (CSV only),
optional `password` (for a protected PDF — used to open the file and never stored).

A PDF is read from its text layer, never by OCR, and never by a language model: ADR-002
keeps model output out of every financial column, and an amount is one. `detected_format` on
the batch reports what was recognised — `sbsa_pdf`, `capitec_pdf`, plain `pdf`, and so on.

**The sign of each amount comes from the running balance**, not from the printed figure.
Statements write a debit as `-1 234,56`, as `1 234,56-`, as `1 234,56 Dr` and as an unmarked
figure, and a debit read as a credit inflates income by the amount spent. Where a balance
column is present, the amount is `balance(n) - balance(n - 1)`, which cannot be ambiguous.

**A statement that does not check out is refused, not imported.** Two checks:

- opening balance + everything read == closing balance;
- no line's printed amount contradicts its own balance movement.

The second is the one that catches a missed line. Because amounts are derived from balance
movements, dropping a line in the middle does not open a gap — the next line's movement
absorbs it and the total still lands on the closing balance. What gives it away is that the
absorbing line's printed amount no longer matches.

```json
{"error": {"code": "validation_error",
           "message": "Some lines on this statement do not match the running balance beside them, so it has not been imported. A line was probably missed or misread.",
           "details": {"rows_read": 84, "lines_in_dispute_count": 1,
                       "lines_in_dispute": ["03 Jul 2026 POS PURCHASE ... 1 234,56 63 865,44"],
                       "format": "sbsa_pdf"}}}
```

Statement quirks the reader handles, learned from real Capitec statements: a `Fee*` column
(so a line carries amount, fee and balance — the balance is always the LAST figure and the
fee belongs to the amount), the VAT marker glued to a figure (`-7.00*`), `R`-prefixed
balances, summary sections before the table whose lines also start with a date, pending card
transactions after it, statements printed newest-first, and rows that print an amount while
the balance does not move (an instalment falling due) — those are reported, not imported.

A loan or credit-card statement is refused: a rising balance there means more owed rather
than more held, and reading it like a cheque account turns an interest charge into income.

Other PDF refusals, each a 400 with `details`: `password_required` for a protected file, and
`text_layer: false` for a scan or a photograph — refused rather than sent to OCR, because a
digit guessed out of an image has no business behind a financial figure.

A file that is neither a statement PDF nor a CSV is a 400 naming what it is, not a 500:

```json
{"error": {"code": "validation_error",
           "message": "This is a PDF. Statement PDFs cannot be read yet — export the same statement as CSV from your bank and upload that.",
           "details": {"detected_type": "pdf"}}}
```

`detected_type` is `pdf`, `spreadsheet` or `binary`, recognised by the file's leading bytes
rather than its name — a PDF renamed `statement.csv` is still a PDF.

### The impact report

`POST /imports` (staging), `GET /imports/{id}/preview`, `POST /imports/{id}/commit`, and
`POST /transactions` all return an `insight` object: what the transactions were, and what
they move.

```json
{
  "months_covered": 6,
  "period_start": "2026-03-01",
  "period_end": "2026-08-31",
  "rows_needing_review": 2,
  "rows": [{ "description": "...", "payment_method": "debit_order",
             "spending_purpose": "rent", "kind": "essential",
             "category_name": "Rent", "category_basis": "rule",
             "needs_review": false }],
  "by_purpose": [{ "key": "rent", "label": "Rent", "total": "87000.00",
                   "monthly_average": "14500.00", "count": 6 }],
  "by_method":  [{ "key": "debit_order", "label": "Debit order", "...": "..." }],
  "commitments": [{ "merchant": "rent property group", "method": "debit_order",
                    "purpose": "rent", "monthly_amount": "14500.00",
                    "occurrences": 6, "is_new": true }],
  "impact": {
    "before": { "income": "52000.00", "essential": "16900.00", "...": "..." },
    "after":  { "income": "52000.00", "essential": "31400.00", "...": "..." },
    "added":  { "income": "0.00", "essential": "14500.00", "...": "..." },
    "changes": [
      { "name": "monthly_cash_flow", "unit": "money",
        "before": "25300.00", "after": "10800.00", "delta": "-14500.00",
        "is_material": true },
      { "name": "emergency_fund_months", "unit": "months",
        "before": "2.852071", "after": "1.535032", "delta": "-1.317039",
        "is_material": true }
    ]
  },
  "affected": [{ "area": "forecast", "effect": "will be marked stale",
                 "detail": "..." }]
}
```

Both sides of every comparison are **monthly averages over the calendar months the file
spans**. A six-month statement adds six months of rent, and charging all of it to one month
would report a cash-flow collapse that did not happen.

`unit` travels with each change so a client never infers from a name whether `0.12` is
twelve cents, twelve percent, or a tenth of a month. `changes` covers `monthly_income`,
`monthly_essential`, `monthly_discretionary`, `monthly_saving`, `monthly_debt_service`,
`monthly_cash_flow`, `liquid_savings`, `cash_flow_margin`, `savings_rate`,
`debt_to_income`, and `emergency_fund_months`.

Emergency-fund cover moves on an import even when no savings balance changed, because
essential spending is its denominator. That is the point of reporting it.

`commitments` is the method-level signal: a debit order is a standing arrangement on its
first appearance, whereas recurrence detection (specs/transactions.md step 6) needs three
occurrences before it will call something a series. The two are reported separately and
labelled as what they are.

---

## Categories

```
GET    /categories
POST   /categories               user-defined only
PATCH  /categories/{id}
DELETE /categories/{id}
```

Deleting a user category reassigns its transactions to the parent, never orphans them. The
response reports how many were reassigned.

---

## Income, expenses, debts, assets

```
GET|POST        /income
GET|PATCH|DELETE /income/{id}
GET|POST        /expenses
GET|PATCH|DELETE /expenses/{id}
GET|POST        /debts
GET|PATCH|DELETE /debts/{id}
GET|POST        /assets
GET|PATCH|DELETE /assets/{id}
```

Inferred records are returned with `"source": "inferred", "is_confirmed": false`. A
`PATCH` setting any field marks the record confirmed, which stops re-inference.

Debt analysis:

```
GET    /debts/{id}/schedule?extra_monthly=
GET    /debts/{id}/what-if?increments=100,500,1000
GET    /debts/strategies?total_monthly=&consolidation_rate=&consolidation_fee=
```

`GET /debts/{id}/schedule` returns the full amortisation, computed synchronously — it is
fast and deterministic. A debt with a `term_months` uses the fixed-term engine (the
instalment is solved); a debt with none (a credit card or store account) is driven by its
`instalment` where set, its `minimum_payment` otherwise.

`GET /debts/{id}/what-if` returns, for each increment in `increments` (default
100/500/1000), the months and interest saved against that same debt's baseline
(`extra_monthly=0`) schedule.

`GET /debts/strategies` compares avalanche and snowball across the user's whole debt set,
plus consolidation when `consolidation_rate` is supplied, returning total interest, months
to free, and the monthly schedule for each. `total_monthly` defaults to the sum of every
debt's minimum payment when omitted. The response states the avalanche-versus-snowball
difference in rand and in months, and whether that difference is material.

---

## Goals

```
GET|POST        /goals
GET|PATCH|DELETE /goals/{id}
GET    /goals/{id}/progress
POST   /goals/{id}/contributions
```

`progress` returns current amount, required monthly contribution to hit the target date,
projected achievement date at current behaviour, and `is_achievable`. Where a goal is not
achievable, the quantified gap is returned rather than an indefinite progress figure, per
requirement 9.

---

## Scenarios

```
POST   /scenarios
GET    /scenarios
GET    /scenarios/{id}
PATCH  /scenarios/{id}
DELETE /scenarios/{id}
POST   /scenarios/{id}/run
GET    /scenarios/{id}/results
GET    /scenarios/{id}/results/{result_id}
POST   /scenarios/{id}/rebaseline
POST   /scenarios/{id}/apply
GET    /scenarios/compare?ids=a,b,c
```

`POST /scenarios` captures a position snapshot at creation and returns
`snapshot_captured_at`. The client displays it.

`POST /scenarios/{id}/run` returns 200 with the result when computation completes within
3 seconds, or 202 with a job identifier when it exceeds that, per the target in
`docs/requirements.md`.

```json
{
  "scenario_id": "...",
  "result_id": "...",
  "engine_version": "1.4.0",
  "computed_at": "2026-09-14T09:12:44+02:00",
  "impact": {
    "monthly_cash_flow_delta": "-8420.15",
    "disposable_income_after": "2379.85",
    "debt_to_income_before": "0.284000",
    "debt_to_income_after": "0.421000",
    "emergency_fund_months_after": "1.02",
    "net_worth_at_60_months": "498300.00",
    "debt_free_date": "2032-09-30"
  },
  "periods": [
    {"month": "2026-10", "cash_flow": "2379.85", "savings": "49100.00",
     "debt": "621100.00", "net_worth": "401200.00"}
  ],
  "baseline_periods": [],
  "assumptions": {}
}
```

`baseline_periods` is the do-nothing comparison, returned alongside so the client renders
before-and-after without a second call. Requirement 5 treats comparison as the point of the
feature, not an extra.

`apply` writes to real financial state. It requires a confirmation token from the response
of a preceding `GET /scenarios/{id}` and produces an audit record. It is the only endpoint
under `/scenarios` that touches real data, per ADR-005.

---

## Forecasting

```
GET    /forecasts/current?horizon_months=60
GET    /forecasts/{id}
POST   /forecasts/refresh
GET    /forecasts/accuracy
```

`GET /forecasts/current` reads stored results and always returns `generated_at` and
`is_stale`. It never computes.

`POST /forecasts/refresh` enqueues regeneration and returns 202.

`GET /forecasts/accuracy` returns prior projections against realised actuals — the feedback
loop in requirement 6.

---

## Analysis

```
GET    /analysis/cash-flow?from=&to=&granularity=month
GET    /analysis/spending?from=&to=&group_by=category
GET    /analysis/trends?from=&to=
GET    /analysis/variance?period=&compare_to=
GET    /analysis/recurring
```

`GET /analysis/variance` decomposes period-over-period change into drivers — income change,
category-level spending change, one-off events, timing — rather than a single total, per
requirement 7. Immaterial variances are excluded server-side against a threshold scaled to
the user's income.

---

## Financial health

```
GET    /health-assessment           ?month=YYYY-MM
GET    /health-assessment/months    ?from=YYYY-MM&to=YYYY-MM
POST   /health-assessment/refresh
```

The score is **per calendar month**. `month` is what an assessment is about; `computed_at`
is only when it was worked out. `GET /health-assessment` with no month returns the most
recent month, which is what the page opens on.

```json
{
  "month": "2026-07",
  "score": 61,
  "computed_at": "2026-09-18T07:12:00+02:00",
  "weights_version": "1.0.0",
  "components": [
    {"name": "emergency_cover", "ratio": "1.530612", "score": "45.000000",
     "weight": "0.250000", "contribution": "11.250000"}
  ],
  "largest_positive_contributor": "credit_utilisation",
  "largest_negative_contributor": "emergency_cover",
  "historical_basis": {
    "monthly_flows": "2026-07",
    "liquid_savings": "2026-07",
    "debt_minimum_payments": "current",
    "credit_utilisation": "current"
  }
}
```

`historical_basis` says which inputs are the month's own and which are as they stand today,
because that decides what a comparison across months means:

- **The month's own** — income, essential, discretionary, saving and debt payments from
  that month's transactions, and liquid savings from that month's closing balance, walked
  back from today's balance through everything that has moved since.
- **As they stand today** — the debts' contractual minimum payments, and card balances and
  limits. Neither is recorded historically: a card's balance in May is nowhere in the data,
  and a debt carries one minimum payment rather than a history of them. So those two
  components are flat across months by construction.

`GET /health-assessment/months` returns the series oldest first, `{"data": [...], "months":
n}`. It replaced `/history`, which was ordered by when each assessment ran — two runs in one
afternoon read as two data points and a quiet fortnight read as none.

`POST /health-assessment/refresh` re-scores the last 12 months and returns the most recent.
Not only the current month: an imported statement usually carries months whose scores were
computed before those transactions existed. Re-scoring a month corrects that month's row
rather than adding a second opinion about the same period.

A month that has not happened yet is a 400.

## Risk flags

```
GET    /risk-flags?status=active
POST   /risk-flags/{id}/acknowledge
POST   /risk-flags/{id}/dismiss
```

Each flag carries `projected_date`, `quantified_amount`, and `computation_reference`
identifying the engine result that produced it. A flag without a computation reference is
not created, per requirement 11.

---

## AI CFO

```
POST   /assistant/ask          {question, conversation_id?}
GET    /assistant/conversations
GET    /assistant/conversations/{id}
DELETE /assistant/conversations/{id}
```

Request and response:

```json
{"question": "Can I afford a R15,000 holiday in December?"}
```

```json
{
  "answer": "Taking R15,000 in December leaves your emergency fund at 0.9 months...",
  "figures": [
    {"label": "Emergency fund after", "value": "0.90", "unit": "months",
     "source": "emergency_fund_engine", "result_id": "..."}
  ],
  "based_on": {
    "accounts": ["..."],
    "period": "2026-03-01/2026-09-14",
    "assumptions": {}
  },
  "supported": true
}
```

Every figure carries the engine and result that produced it. `figures` is the authoritative
content; `answer` is narration over it, per ADR-002.

When no engine can answer, the response is `"supported": false` with an explanation of what
the system cannot yet model. It does not approximate.

When the model provider is unavailable, the endpoint returns the figures with `answer:
null` and `"narration_available": false`. The client renders the numbers, per requirement 12.

`DELETE /assistant/conversations/{id}` removes a conversation and its messages, and returns
204. A hard delete, unlike the financial tables: the transcript holds a question and
narration over figures stored elsewhere and recomputed on every ask, so deleting it destroys
no financial record — the same reasoning that has scenarios hard delete (docs/database.md
§1). A conversation belonging to another user is a 404, the same answer as one that does not
exist.

Wording note: `source` on a figure names the engine that produced it and stays that way —
it is the provenance ADR-002 requires. The client maps it to plain words before showing it,
so a reader sees "from your emergency fund" and never `emergency_fund_engine`. The same goes
for `engine_version` on a forecast: stored, returned, and not rendered.

---

## Data and account management

```
GET    /export                 full data export, async, returns 202
GET    /export/{id}
DELETE /account                requires password confirmation
```

---

## Operational

```
GET    /health                 liveness, unauthenticated
GET    /ready                  readiness including database and queue
```

---

## Rate limits

| Scope | Limit |
|---|---|
| Authentication | 5 / 15 min per email and per IP |
| Assistant | 30 / hour per user |
| Scenario run | 60 / hour per user |
| Import | 10 / hour per user |
| General | 300 / min per user |

Exceeding a limit returns 429 with `Retry-After`.

---

## Versioning

Breaking changes go to `/api/v2`. Within a version, fields may be added but never removed
or retyped. Money never becomes a JSON number, in any version.
