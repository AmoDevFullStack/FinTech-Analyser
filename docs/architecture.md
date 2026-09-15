# Architecture

This file is the structural source of truth for the Financial Digital Twin. Read it
before making any change that adds a file, moves logic between layers, or introduces a
dependency. Where this file and the code disagree, this file wins and the code is a bug.

Behaviour lives in `specs/`. Decisions that should not be casually reversed live in
`docs/decisions.md`. The data model lives in `docs/database.md`. The HTTP contract lives
in `docs/api.md`. Frontend structure is expanded in `docs/frontend.md` and appearance in
`docs/design-system.md`. This file describes structure only.

---

## 1. The organising idea

The system is a deterministic financial core surrounded by surfaces. The core computes;
the surfaces present, schedule, and narrate.

```
React + TypeScript          surface
        ↓
REST API (Flask)            surface
        ↓
Application services        core
        ↓
Domain engines              core
        ↓
Repositories                core
        ↓
PostgreSQL                  persistence
```

Background workers and the LLM layer attach at the application-service boundary. They
are surfaces, not core.

Every dependency arrow points downward. A layer may call the layer directly below it. A
layer may not call the layer above it, and may not skip a layer. Concretely: a route
never imports a repository, a repository never imports a domain engine, and a domain
engine never imports anything from the application, API, or infrastructure packages.

---

## 2. Backend layout

```
backend/
└── app/
    ├── api/                  HTTP layer, one module per resource
    │   └── v1/
    ├── services/             application services, one per use case family
    ├── domain/               deterministic financial engines
    ├── repositories/         data access
    ├── models/               SQLAlchemy ORM models
    ├── schemas/              request/response serialisation
    ├── workers/              background jobs
    ├── llm/                  prompt construction and model calls
    ├── integrations/         external providers behind interfaces
    └── core/                 config, errors, auth primitives, money helpers
```

Module names are plural nouns. Files inside them are singular: `services/scenario.py`
defines `ScenarioService`, `repositories/transaction.py` defines
`TransactionRepository`, `domain/amortisation.py` defines free functions.

---

## 3. Layer contracts

### 3.1 API layer — `app/api/`

Responsible for HTTP and nothing else: routing, deserialising the request, enforcing
authentication, calling exactly one application service, serialising the result, and
choosing a status code.

A route handler should be readable in one screen. If it contains a conditional that
depends on a financial value, the logic is in the wrong place.

```python
@bp.post("/scenarios/<uuid:scenario_id>/run")
@require_auth
def run_scenario(scenario_id: UUID) -> tuple[Response, int]:
    result = scenario_service.run(user_id=g.user_id, scenario_id=scenario_id)
    return jsonify(ScenarioResultSchema().dump(result)), 200
```

Must not contain: financial arithmetic, SQLAlchemy queries, `db.session`, business
conditionals, or direct calls to the LLM layer.

Errors: services raise domain exceptions from `app/core/errors.py`; a single error
handler maps them to status codes. Route handlers do not catch exceptions to translate
them.

### 3.2 Application services — `app/services/`

Responsible for orchestrating a use case: load what is needed through repositories, call
domain engines, persist results, enqueue follow-up work, and return a result object.

This is the only layer permitted to open a transaction boundary. A service method is the
unit of atomicity — either the whole use case commits or none of it does.

```python
class ScenarioService:
    def run(self, *, user_id: UUID, scenario_id: UUID) -> ScenarioResult:
        scenario = self._scenarios.get_for_user(scenario_id, user_id=user_id)
        position = self._positions.current_for_user(user_id)
        projection = project_scenario(position=position, assumptions=scenario.assumptions)
        return self._results.save(scenario_id=scenario_id, projection=projection)
```

Services may call other services, but only downward through a deliberate hierarchy — if
two services need each other, the shared logic belongs in a domain engine.

Must not contain: raw SQL, formulas, or HTTP concepts such as status codes.

### 3.3 Domain engines — `app/domain/`

Responsible for the financial mathematics. This is the layer the whole product rests on.

Domain engines are pure functions over values. No database session, no network call, no
clock read, no randomness, no logging of financial values. Anything varying — today's
date, an interest rate, an inflation assumption — arrives as an explicit argument.

```python
def amortisation_schedule(
    *,
    principal: Decimal,
    annual_rate: Decimal,
    term_months: int,
    extra_monthly: Decimal = Decimal("0"),
) -> list[AmortisationPeriod]:
    ...
```

Every engine takes and returns `Decimal`, never `float`. Every engine is paired with a
test asserting against independently derived reference figures. Rounding happens at
defined boundaries and is documented in the docstring, not applied ad hoc.

Must not contain: imports from `services`, `repositories`, `api`, `models`, or `llm`.
The domain package should be importable in a process with no database configured. A test
that enforces this is worth writing.

### 3.4 Repositories — `app/repositories/`

Responsible for getting rows in and out of PostgreSQL. Query construction, eager-loading
strategy, pagination, and nothing else.

Every method that reads or writes a user-owned record takes `user_id` as a keyword
argument and applies it as a filter. Scoping is enforced here rather than in routes,
because a repository method that can return another user's rows is a vulnerability
waiting for someone to call it from a new place.

Queries use bound parameters. Never interpolate values into SQL strings — pass them as
parameters and let the driver handle them.

```python
def by_account(
    self, account_id: UUID, *, user_id: UUID, since: date | None = None
) -> list[Transaction]:
    stmt = select(Transaction).where(
        Transaction.account_id == account_id,
        Transaction.user_id == user_id,
    )
    if since is not None:
        stmt = stmt.where(Transaction.occurred_on >= since)
    return list(self._session.scalars(stmt))
```

Must not contain: business rules, financial calculations, or commit calls. Repositories
flush; services commit.

### 3.5 Workers — `app/workers/`

Responsible for running work that is too slow for a request: transaction import,
categorisation, forecast materialisation, scheduled health evaluation, notifications.

A worker is a thin entry point that calls the same application service the API would.
There must never be two implementations of a calculation, one synchronous and one
asynchronous.

Jobs are idempotent. Re-running a forecast job for the same user and period replaces the
prior result rather than appending a second one.

### 3.6 LLM layer — `app/llm/`

Responsible for turning computed results into language, and for classifying what a user's
question is asking for. It is an interpretation layer, and this boundary is the product's
central claim — see ADR-002.

The LLM may: explain a computed result, summarise behaviour the analytics layer
identified, compare two scenarios the engine already ran, and phrase a recommendation the
rules engine produced.

The LLM may not: compute or estimate any figure, query the database directly, write to
any financial field, or be the only path by which a user obtains an answer. If the model
is unavailable, the user still receives the numbers — without narration.

Prompts are constructed from a result object, never from raw table rows, and carry only
the minimum financial context the request requires.

### 3.7 Integrations — `app/integrations/`

External providers — banking aggregators, credit bureaux, market data — sit behind an
interface defined in this package. Services depend on the interface, never on a vendor
SDK. Each integration owns its own retry, timeout, and rate-limit handling, and
translates vendor errors into domain exceptions.

---

## 4. Frontend

This section states the rules the whole system depends on. The layer contracts, the
`Money` type, server-state ownership, and routing are expanded in `docs/frontend.md`;
appearance and the treatment of projected figures are in `docs/design-system.md`.

```
frontend/src/
├── pages/          route-level compositions
├── features/       one folder per capability, colocating components and hooks
├── components/     shared presentational components
├── api/            generated or hand-written client, typed against docs/api.md
├── hooks/
└── lib/            formatting, dates, display-only helpers
```

The frontend performs no financial calculations. Not a sum, not a percentage, not a
projected balance. If a number appears on screen, the API supplied it. This is not
stylistic — two implementations of a formula in two languages will drift, and the one
users see will be the wrong one.

`lib/` may format values for display: currency symbols, thousand separators, date
formatting, rounding for presentation. Formatting is not calculation.

Money crosses the wire as a string, not a JSON number, so precision survives the trip.
The client parses it for display and never for arithmetic.

---

## 5. Rules that apply everywhere

**Money is `Decimal` in Python and `NUMERIC(15, 2)` in PostgreSQL.** Never `float`, never
a JSON number in an API response. See ADR-001.

**Every financial record is user-scoped**, and scoping is enforced in the repository
layer.

**Real state and hypothetical state are separate.** A scenario references a snapshot; it
never mutates accounts, transactions, debts, income, or goals. Applying a scenario is an
explicit, separate, audited operation. See ADR-005.

**Every stored figure is reproducible** from its persisted inputs. Store the assumptions
alongside the result, not just the result.

**Timestamps everywhere.** `created_at` and `updated_at` on every table. Soft delete
wherever historical integrity matters.

**Python is typed, 3.12+ style.** `list[Transaction]`, `Decimal | None`, `dict[str, Any]`
— not `List`, not `Optional`. Keyword-only arguments for anything financial, so call
sites are unambiguous about which figure is which.

**No new dependency without an entry in `docs/decisions.md`.**

---

## 6. Testing shape

| Layer | What is tested | Tool |
|---|---|---|
| Domain engines | Reference figures, invariants, edge cases | pytest, hypothesis |
| Repositories | Query correctness, user scoping | pytest + real Postgres |
| Services | Orchestration, transaction boundaries | pytest with fake repositories |
| API | Contract conformance to `docs/api.md` | pytest + test client |
| Frontend | Component behaviour | Vitest |
| End to end | Scenario creation through result display | Playwright |

Domain engine tests are the ones that matter most and are cheapest to write, because the
engines are pure. Expected values come from an independent source — a spreadsheet model,
a published formula worked by hand — never from running the code under test and pasting
the output.

---

## 7. When you are about to add something

Ask where it belongs before writing it:

- Does it perform arithmetic on money? → `domain/`
- Does it coordinate several steps to fulfil a user action? → `services/`
- Does it read or write rows? → `repositories/`
- Does it speak HTTP? → `api/`
- Does it call an external provider? → `integrations/`
- Does it produce prose for a human? → `llm/`

If the answer is "several of these", it is several things and should be split.

If the change contradicts this file, update this file in the same pull request and add an
ADR if it reverses a recorded decision. Do not leave the document and the code
disagreeing.
