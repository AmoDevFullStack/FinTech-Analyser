# API specification

Base URL: `/api/v1`

This file is the contract. Code follows it, not the other way round. Contract tests assert
that responses match what is written here — if you change an endpoint, change this file in
the same pull request or the tests will fail, which is the intended behaviour.

---

## Conventions

**Authentication** is a session cookie, `HttpOnly`, `Secure`, `SameSite=Lax`. Every
endpoint except `/auth/register`, `/auth/login`, and `/health` requires it.

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
POST   /auth/logout
GET    /auth/me
POST   /auth/password-reset          {email}
POST   /auth/password-reset/confirm  {token, password}
POST   /auth/mfa/enroll
POST   /auth/mfa/verify              {code}
```

`GET /auth/me` returns the user without financial data. Position comes from
`/position`, because identity and financial state are different concerns with different
cache behaviour.

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
GET    /transactions?account_id=&from=&to=&category_id=&min_amount=&max_amount=&q=
POST   /transactions
GET    /transactions/{id}
PATCH  /transactions/{id}
DELETE /transactions/{id}
POST   /transactions/bulk-categorise   {transaction_ids[], category_id}
```

Import is a separate resource because it is a multi-step process with its own state:

```
POST   /imports                        multipart CSV upload
GET    /imports/{id}                   status, counts, detected format
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
GET    /health-assessment
GET    /health-assessment/history?from=&to=
POST   /health-assessment/refresh
```

The response includes the component breakdown. A score without its components is not a
valid response, per requirement 10.

`POST /health-assessment/refresh` computes a fresh assessment synchronously and returns
201 with it — the on-demand counterpart to `POST /position/snapshot`. Scheduled and
material-change recomputation (specs/financial-health.md) go through the same service via
a worker; there is exactly one implementation of the calculation, per
docs/architecture.md §3.5.

---

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
