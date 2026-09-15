# Database design

PostgreSQL is the single source of truth for financial state. This file defines the
entities, their relationships, and the rules that apply to every table. Schema changes
require updating this file in the same pull request.

Migrations are Alembic. Every migration is reversible, and any migration touching
financial columns is tested against a copy of realistic data before it runs anywhere real.

---

## 1. Rules that apply to every table

**Money is `NUMERIC(15, 2)`.** Rates and ratios are `NUMERIC(9, 6)`. Never `DOUBLE
PRECISION`, never `REAL`, never a float anywhere in a financial column. See ADR-001.

**Every financial record carries `user_id`** as a non-null foreign key, indexed, and every
query filters on it at the repository layer. A table holding financial data without
`user_id` is a design error, even when ownership could be derived through a join.

**Every table carries `created_at` and `updated_at`**, both `TIMESTAMPTZ NOT NULL DEFAULT
now()`. `updated_at` is maintained by trigger, not by application code, so it cannot be
forgotten.

**Primary keys are UUID v7** where available, v4 otherwise. Sequential integers leak record
counts and make enumeration attacks trivial on a financial API.

**Soft delete where history matters** — accounts, transactions, debts, goals carry
`deleted_at TIMESTAMPTZ NULL`. Scenarios and their results hard delete, because a discarded
hypothetical has no historical value. Partial indexes exclude soft-deleted rows.

**Dates versus timestamps.** A transaction has an `occurred_on DATE` — banks report a date,
not a moment. Audit fields are `TIMESTAMPTZ`. Never store a financial event date as a
timestamp in a local timezone; the day boundary will move.

**Enumerations are Postgres enums** where the set is closed and stable (account type,
scenario type), and lookup tables where the user can extend them (categories).

---

## 2. Entity map

```
User
 ├── Account ──────── Transaction ──── Category
 ├── Income
 ├── Expense
 ├── Debt ─────────── DebtPayment
 ├── Asset
 ├── Goal ─────────── GoalContribution
 ├── CreditProfile
 ├── PositionSnapshot
 ├── Scenario ─────── ScenarioAssumption
 │                └── ScenarioResult
 ├── Forecast ─────── ForecastPeriod
 ├── HealthAssessment
 └── RiskFlag
```

Real financial state is on the left branch. Hypothetical state — `PositionSnapshot`,
`Scenario`, `ScenarioAssumption`, `ScenarioResult` — is structurally separate and never
writes to the real branch. See ADR-005.

---

## 3. Core entities

### User

Identity and authentication only. Financial attributes live in the entities below, not
here, so that "the user's financial position" is always a computed value rather than a set
of fields that can drift.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| email | CITEXT | unique, case-insensitive |
| password_hash | TEXT | argon2id |
| full_name | TEXT | |
| currency | CHAR(3) | ZAR for v1 |
| timezone | TEXT | IANA identifier |
| mfa_secret | TEXT NULL | |
| last_login_at | TIMESTAMPTZ NULL | |

### Account

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK, indexed |
| name | TEXT | |
| account_type | account_type_enum | transactional, savings, credit_card, loan, home_loan, vehicle_finance, investment, manual_asset |
| institution | TEXT NULL | |
| current_balance | NUMERIC(15,2) | |
| balance_source | balance_source_enum | derived or manual |
| credit_limit | NUMERIC(15,2) NULL | credit accounts only |
| interest_rate | NUMERIC(9,6) NULL | annual nominal |
| opened_on | DATE NULL | |
| archived_at | TIMESTAMPTZ NULL | |
| deleted_at | TIMESTAMPTZ NULL | |

`balance_source` exists because a derived balance and a typed-in balance carry different
reliability, and the UI must be able to say which it is showing.

### Transaction

The highest-volume table. Indexing decisions here matter more than anywhere else.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK, indexed |
| account_id | UUID | FK, indexed |
| category_id | UUID NULL | FK |
| occurred_on | DATE | indexed |
| posted_on | DATE NULL | when the bank posted it |
| amount | NUMERIC(15,2) | signed; negative is outflow |
| description | TEXT | as supplied by the institution |
| normalised_description | TEXT | cleaned, used for matching |
| direction | direction_enum | debit or credit, derived but stored |
| transfer_group_id | UUID NULL | links both legs of an internal transfer |
| is_recurring | BOOLEAN | set by the recurrence detector |
| recurrence_group_id | UUID NULL | links instances of one recurring series |
| category_confidence | NUMERIC(9,6) NULL | null when user-set |
| category_set_by_user | BOOLEAN | corrections are never overwritten |
| import_batch_id | UUID NULL | FK, for undoing an import |
| external_id | TEXT NULL | institution's identifier where supplied |
| fingerprint | TEXT | deduplication hash |
| deleted_at | TIMESTAMPTZ NULL | |

Sign convention: outflows are negative, inflows positive, for every account type including
credit cards. A credit card purchase is negative; a payment to the card is positive. This
is stated once here and never varied, because a mixed convention is the single most
reliable way to produce a wrong net figure.

`fingerprint` is a hash over `user_id`, `account_id`, `occurred_on`, `amount`, and
`normalised_description`. Unique partial index on non-deleted rows. It catches exact
re-imports; near-duplicates go through the matching flow in `specs/transactions.md`.

Indexes: `(user_id, occurred_on DESC)` for history, `(account_id, occurred_on)` for balance
derivation, `(user_id, category_id, occurred_on)` for category analysis,
`(recurrence_group_id)` for series lookup.

### Category

Hierarchical, one level deep. System categories are seeded and shared; user categories
carry a `user_id`.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID NULL | null for system categories |
| parent_id | UUID NULL | FK, self |
| name | TEXT | |
| kind | category_kind_enum | income, essential, discretionary, debt, saving, transfer |

`kind` drives the cash-flow and health engines. Discretionary and essential spending
behave differently in a projection, and the distinction must be structural rather than
inferred from the name.

### Income and Expense

Recurring commitments the user has declared, distinct from observed transactions. These
are the projection's baseline where history is thin.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK |
| label | TEXT | |
| amount | NUMERIC(15,2) | |
| frequency | frequency_enum | weekly, fortnightly, monthly, quarterly, annually |
| next_due_on | DATE | |
| category_id | UUID NULL | FK |
| is_confirmed | BOOLEAN | false when inferred, true when user-confirmed |
| source | source_enum | declared or inferred |

Per requirement 1, an inferred value the user has corrected is never silently re-inferred.
`is_confirmed` is what enforces that.

### Debt

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK |
| account_id | UUID NULL | FK, where the debt is also a tracked account |
| debt_type | debt_type_enum | credit_card, personal_loan, vehicle, home_loan, store_account, other |
| original_principal | NUMERIC(15,2) | |
| current_balance | NUMERIC(15,2) | |
| annual_rate | NUMERIC(9,6) | nominal |
| minimum_payment | NUMERIC(15,2) | |
| instalment | NUMERIC(15,2) NULL | contractual, where fixed |
| term_months | INTEGER NULL | |
| started_on | DATE | |
| deleted_at | TIMESTAMPTZ NULL | |

### Asset and Goal

`Asset` holds non-account holdings — property, vehicles, valuables — with a value and a
valuation date, because a stale valuation presented as current inflates net worth.

`Goal` holds target amount, target date, current amount, priority, and linked account.
`GoalContribution` records actual movements toward it, so progress is evidenced rather
than asserted.

### CreditProfile

Score, bureau, retrieved date, and the factors supplied. Nullable throughout — most users
will have none in v1, and every consumer must handle absence.

---

## 4. Hypothetical entities

### PositionSnapshot

A frozen copy of the user's computed position at a moment, stored as a typed JSONB document
plus the scalar fields the engines need directly.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK |
| captured_at | TIMESTAMPTZ | |
| net_worth | NUMERIC(15,2) | |
| monthly_income | NUMERIC(15,2) | |
| monthly_essential | NUMERIC(15,2) | |
| monthly_discretionary | NUMERIC(15,2) | |
| total_debt | NUMERIC(15,2) | |
| liquid_savings | NUMERIC(15,2) | |
| position | JSONB | full structured position |

JSONB here is deliberate and is the one place structured financial data is denormalised. A
snapshot is immutable and is never queried across users, so relational decomposition buys
nothing. Money inside the JSONB is stored as a string, never a JSON number, for the reason
in ADR-001.

### Scenario, ScenarioAssumption, ScenarioResult

`Scenario` holds name, description, type, `snapshot_id`, and status.
`ScenarioAssumption` holds typed key-value assumptions — purchase price, deposit, rate,
term, additional monthly cost, income delta.
`ScenarioResult` holds the projection output plus `assumptions_hash` and `engine_version`.

`assumptions_hash` and `engine_version` are what make a stored result reproducible. When
an engine changes such that a stored result would no longer be reproduced, that is a
behavioural change — see the closing section of the `financial-domain-engine` skill.

Constraint: no foreign key from any real financial table to a scenario table. The
dependency runs one way only. A test asserts that a scenario run issues zero writes to
real tables.

---

## 5. Derived entities

### Forecast and ForecastPeriod

`Forecast` holds `user_id`, `horizon_months`, `generated_at`, `input_snapshot_id`,
`assumptions` (JSONB), `engine_version`, and `is_stale`.
`ForecastPeriod` holds one row per projected month: period index, month, projected income,
expenses, cash flow, savings balance, debt balance, emergency fund months, and net worth.

Rows accumulate. Retention: keep all forecasts from the last 90 days, then one per month,
because forecast history is what makes accuracy measurement possible (requirement 6).

### HealthAssessment

Score, computed date, and a JSONB breakdown of component contributions. The breakdown is
not optional — requirement 10 demands the score be inspectable, and a score stored without
its components cannot be explained after the fact.

### RiskFlag

Type, severity, detected date, projected date, quantified amount, status
(active, acknowledged, resolved), and the computation reference that produced it. A flag
without a computation reference cannot be explained and must not be created.

---

## 6. Audit

`AuditLog` records any action that writes to real financial state: scenario applied,
balance manually adjusted, account archived, import undone, data exported, account deleted.

Columns: `user_id`, `action`, `entity_type`, `entity_id`, `before` (JSONB), `after`
(JSONB), `actor` (user or system), `occurred_at`.

Append-only. No update or delete path exists in the repository layer.

---

## 7. Things deliberately not done

**No materialised current balance on `User`.** Position is computed and snapshotted, never
maintained as a mutable field, because a denormalised balance drifts and drift in this
system is indistinguishable from a bug in the engines.

**No `is_hypothetical` flag on real tables.** Rejected in ADR-005 for the reason given
there.

**No storage of raw provider payloads in financial tables.** Import staging is separate and
purged after successful import, so vendor shape never leaks into the domain model.
