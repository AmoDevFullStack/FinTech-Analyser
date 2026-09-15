# Architecture decisions

Decisions recorded here have been made deliberately and should not be reversed casually.
If you are an agent working in this repository and a change would contradict one of
these, stop and raise it rather than implementing around it.

Each record states what would have to be true to revisit it. That clause is the
useful part — a decision with no revisit condition is dogma, not engineering.

---

# ADR-001: Represent money as Decimal and NUMERIC

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

Every figure this system produces is money or derived from money. Projections compound
over 60 monthly periods, amortisation schedules iterate hundreds of times, and net-worth
calculations sum across dozens of accounts. Representation error at each step accumulates.

The product's claim is that its numbers are reproducible and auditable. A user who runs
the same scenario twice and sees R4,312.67 then R4,312.66 has been given a reason to
distrust everything else on the screen.

Representation choice touches the database schema, the ORM models, the domain engines,
the serialisation layer, and the frontend. It is the single most expensive decision here
to reverse.

## Decision

Money is `NUMERIC(15, 2)` in PostgreSQL and `decimal.Decimal` in Python, end to end.
Rates and ratios are `NUMERIC(9, 6)`. Money crosses the API as a JSON string, never a
JSON number. Rounding is applied at explicit, documented boundaries — never incidentally.

`float` may not appear in any code path that touches a monetary value. This includes
intermediate calculations inside domain engines.

## Options considered

### Option A: NUMERIC + Decimal

| Dimension | Assessment |
|---|---|
| Complexity | Low — native support in both Postgres and Python |
| Correctness | Exact for base-10 arithmetic |
| Performance | Slower than float; irrelevant at our volumes |
| Team familiarity | High |

**Pros:** exact decimal arithmetic, no representation surprises, `NUMERIC` is what every
financial system uses, SQLAlchemy maps it to `Decimal` without ceremony.
**Cons:** requires discipline at every boundary — JSON, NumPy, pandas, and the frontend
all want to hand you floats.

### Option B: Integer minor units (store cents)

| Dimension | Assessment |
|---|---|
| Complexity | Medium — every read and write needs conversion |
| Correctness | Exact for addition; awkward for rates and division |
| Performance | Fastest |
| Team familiarity | Medium |

**Pros:** exact, fast, impossible to accidentally introduce a float, common in payments
systems.
**Cons:** interest calculations and ratios need conversion in and out constantly, which
is its own error surface; raw database rows become unreadable during debugging; a
currency with three decimal places would require a migration.

### Option C: Float / DOUBLE PRECISION

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Correctness | Inexact by construction |
| Performance | Fast |
| Team familiarity | High |

**Pros:** nothing to think about, works with NumPy and pandas directly.
**Cons:** 0.1 + 0.2 ≠ 0.3, errors compound across 60 projection periods, and no
plausible defence if a user challenges a figure.

## Trade-off analysis

Option C is disqualified: the product's central claim is reproducibility, and float
cannot deliver it.

Between A and B, the deciding factor is that this system does far more multiplication and
division than a payments system does. Interest accrual, debt-to-income ratios, savings
rates, and inflation adjustment all involve rates. Option B's advantage — exactness under
addition — is exactly the operation Option A also handles exactly, while Option A handles
the rate arithmetic without conversion ceremony. The readability of `NUMERIC` columns in
production debugging is a real secondary benefit.

Option A's weakness is discipline at boundaries. That is addressable with tooling: the
serialisation layer, a lint rule, and the `financial-domain-engine` skill all enforce it.

## Consequences

- Domain engines are written against `Decimal` throughout, including intermediates.
- The data-science layer cannot pass NumPy or pandas floats into financial calculations.
  Statistical analysis may use float internally; the boundary back into the engine
  converts explicitly and the conversion point is documented.
- API schemas serialise money as strings. Frontend types reflect this and never perform
  arithmetic on the value.
- A lint rule and a CI check should reject `float` in `app/domain/`.
- Rounding policy must be stated per engine, not assumed.

## Revisit if

A requirement appears for a currency with other than two minor units, or profiling shows
`Decimal` arithmetic is a genuine bottleneck in forecast generation — which would be
surprising at per-user volumes.

## Action items

1. [ ] Define `Money = Decimal` alias and helpers in `app/core/money.py`.
2. [ ] Set SQLAlchemy column type and Marshmallow field for money once, centrally.
3. [ ] Add CI check rejecting `float` in `app/domain/`.
4. [ ] Record the rounding convention in `docs/database.md`.

---

# ADR-002: The LLM is an interpretation layer, never a calculation engine

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

The product is marketed as AI-powered and includes an "AI CFO" that answers questions like
"can I afford a R15,000 holiday?". The obvious implementation is to hand the model the
user's financial context and let it answer.

Language models produce plausible arithmetic. Plausible is not the same as correct, and
the failure is silent — a wrong figure arrives with the same confident tone as a right
one. Worse, it is not reproducible: the same question can yield different numbers.

This project's differentiator is that its projections are trustworthy. That claim does
not survive the model being in the calculation path.

## Decision

Financial figures are produced exclusively by deterministic Python in `app/domain/`. The
LLM receives an already-computed result object and turns it into language.

The model may classify intent, explain a result, summarise identified patterns, compare
scenarios the engine already ran, and phrase a recommendation the rules engine produced.

The model may not compute or estimate a figure, query the database, write to a financial
field, or be the only path by which a user obtains an answer.

A question flows: user question → intent classification → context assembly from verified
state → scenario or forecast engine → persisted result → LLM explanation.

## Options considered

### Option A: LLM as interpretation layer only

| Dimension | Assessment |
|---|---|
| Complexity | Medium — requires intent classification and result objects |
| Correctness | Deterministic, testable, reproducible |
| Latency | Two hops, but the engine hop is fast |
| Flexibility | Limited to questions the engine can answer |

**Pros:** every figure is auditable and reproducible; the app degrades gracefully when
the model is unavailable; prompt injection cannot alter a financial figure.
**Cons:** questions outside the engine's repertoire cannot be answered at all; each new
question type needs engine work rather than a prompt tweak.

### Option B: LLM with tool access to financial data

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Correctness | Non-deterministic; correct figures, unreliable arithmetic on them |
| Latency | Multiple tool round-trips |
| Flexibility | High |

**Pros:** handles unanticipated questions; less engine work per question type.
**Cons:** the model still does the arithmetic on retrieved values, so the reproducibility
problem remains; harder to audit; the authorisation surface widens considerably.

### Option C: LLM answers directly from context

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Correctness | Unacceptable |
| Latency | Single hop |
| Flexibility | Highest |

**Pros:** fastest to build, handles anything.
**Cons:** invented figures, no reproducibility, no audit trail. Disqualifying for a
product whose thesis is trustworthy projection.

## Trade-off analysis

Option C is incompatible with the product thesis. Option B is the tempting middle: it
feels safer than C because the data is real. But the arithmetic is still performed by a
non-deterministic system, which is precisely the property that matters. Retrieved-then-
computed is not meaningfully more auditable than invented.

Option A's genuine cost is inflexibility — a question the engine cannot answer gets no
answer. That is the right failure mode for this product. "I can't project that yet" is
recoverable; a confident wrong number is not.

## Consequences

- Every AI-answerable question requires a corresponding engine capability. The engine
  repertoire becomes a product roadmap item in its own right.
- Intent classification becomes a component with its own tests and a defined fallback for
  unrecognised intent.
- Prompts are built from result objects, not raw rows, which also limits how much
  financial data reaches the provider.
- The app remains functional with the model disabled — the numbers render without prose.
- Response latency includes both an engine run and a model call.

## Revisit if

Deterministic, verifiable tool-use with formal output guarantees becomes available, or a
class of genuinely valuable questions emerges that cannot be expressed as engine
capabilities. Even then, computed figures stay with the engine.

## Action items

1. [ ] Define the `FinancialResult` contract every LLM prompt is built from.
2. [ ] Implement intent classification with an explicit "not supported" path.
3. [ ] Add a test asserting no LLM response is ever persisted to a financial column.
4. [ ] Document the boundary in `specs/ai-cfo.md`.

---

# ADR-003: Forecasts are materialised asynchronously

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

A 60-month projection across cash flow, savings, debt, emergency fund, and net worth reads
the user's full transaction history, derives behavioural parameters, and iterates monthly.
This is seconds of work, not milliseconds, and it grows with account history.

The dashboard is the most-visited screen in the product and must feel instant.

## Decision

Forecasts are computed by background workers and persisted. The API reads stored forecast
rows and never computes a projection during a request.

Forecasts are regenerated on a schedule, on material change (transaction import, income
change, new debt), and on explicit user request. Each stored forecast carries the
assumptions and input snapshot it was generated from, plus a `generated_at` timestamp.

The staleness contract: the UI displays when a forecast was generated. A forecast known to
be stale is labelled as such rather than silently refreshed or silently served.

Scenario runs are the exception — they are user-initiated, expected to take a moment, and
run synchronously with a visible progress state, up to a timeout after which they fall
back to the queue.

## Options considered

### Option A: Asynchronous materialisation

| Dimension | Assessment |
|---|---|
| Complexity | Medium — requires a queue, worker, invalidation rules |
| Read latency | Milliseconds |
| Freshness | Eventual, bounded and disclosed |
| Infrastructure | Redis plus a worker process |

**Pros:** fast dashboard, expensive work batched, natural fit for scheduled evaluation
and notifications, forecast history retained for free.
**Cons:** an extra moving part; invalidation logic is a real source of bugs; users can
see a stale projection.

### Option B: Compute on request with caching

| Dimension | Assessment |
|---|---|
| Complexity | Low initially |
| Read latency | Fast on hit, seconds on miss |
| Freshness | Always current on miss |
| Infrastructure | Cache only |

**Pros:** simpler, no worker, always fresh when it runs.
**Cons:** the cold path is the first visit of the day, which is the visit that matters;
cache invalidation is the same problem as forecast invalidation with worse ergonomics;
no forecast history, so forecast-versus-actual accuracy cannot be measured.

### Option C: Compute on every request

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Read latency | Seconds, every time |
| Freshness | Always current |
| Infrastructure | None |

**Pros:** trivially correct, no staleness.
**Cons:** unusable dashboard; cost scales with page views rather than data changes.

## Trade-off analysis

Option C fails the primary interaction. Option B is Option A with the queue replaced by a
cache, and loses something valuable: persisted forecast history is what makes
forecast-versus-actual variance analysis possible later, and that is a genuine product
capability rather than an implementation detail.

The cost of Option A is invalidation complexity and disclosed staleness. Disclosure turns
the weakness into an honesty feature — showing "projected as of 14 September" is more
trustworthy than a number that silently changes between visits.

## Consequences

- Redis and a worker process become required infrastructure from day one.
- Invalidation rules must be explicit and tested — which events dirty a forecast.
- The UI needs a generated-at indicator and a manual refresh affordance.
- Forecast rows accumulate; a retention policy is needed.
- Forecast-versus-actual accuracy becomes measurable, feeding the variance engine.

## Revisit if

Projection cost falls far enough that sub-100ms synchronous generation is realistic, or
forecast history proves to have no analytical use.

## Action items

1. [ ] Choose the queue (RQ for simplicity, Celery if scheduling grows complex).
2. [ ] Define the dirty-event list that triggers regeneration.
3. [ ] Add `generated_at` and input snapshot columns to the forecast table.
4. [ ] Specify the staleness threshold and its UI treatment in `specs/forecasting.md`.

---

# ADR-004: Flask as the backend framework

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

The backend serves a REST API, runs synchronous financial computation, coordinates
background jobs, and integrates with the Python data-science ecosystem for behavioural
analysis and forecasting.

Framework choice affects developer velocity, the shape of the async story, and how much
scaffolding the project carries.

## Decision

Flask with SQLAlchemy and Alembic. Do not replace it with another framework unless the
revisit condition below is met.

## Options considered

### Option A: Flask

| Dimension | Assessment |
|---|---|
| Complexity | Low — minimal, explicit, unopinionated |
| Data-science fit | Excellent |
| Async | Synchronous by default; workers handle long jobs |
| Team familiarity | High |

**Pros:** stays out of the way, which suits an architecture with strong self-imposed
layering; mature SQLAlchemy and Alembic integration; the whole ecosystem is synchronous
Python, which matches how the domain engines are written.
**Cons:** no built-in validation or OpenAPI generation, so schemas are hand-written; async
endpoints are awkward if ever needed.

### Option B: FastAPI

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Data-science fit | Excellent |
| Async | Native |
| Team familiarity | Medium |

**Pros:** Pydantic validation and automatic OpenAPI, which would keep `docs/api.md`
honest; async-native; excellent typing story.
**Cons:** async offers little here because the workload is CPU-bound arithmetic and
database reads, not fan-out I/O; mixing sync ORM calls into async handlers is a known
foot-gun.

### Option C: Django + DRF

| Dimension | Assessment |
|---|---|
| Complexity | High — brings an ORM, admin, auth, and opinions |
| Data-science fit | Good |
| Async | Partial |
| Team familiarity | Medium |

**Pros:** batteries included, admin interface is genuinely useful for inspecting
financial records during development, mature auth.
**Cons:** the Django ORM is harder to confine behind a repository layer, and the
framework's conventions actively fight the layering this project depends on.

## Trade-off analysis

Option C's conventions pull against the architecture. Django wants fat models and views
that query directly; this project wants pure domain functions and a repository boundary.
Fighting a framework's grain for the life of a project is a poor trade for an admin panel.

Option A versus B is close, and FastAPI's automatic OpenAPI is a real loss to accept —
`docs/api.md` will need discipline to stay accurate. The deciding factor is that async
buys nothing for a CPU-bound, worker-offloaded workload, while the async/sync boundary
adds a class of bug that does not otherwise exist. Flask's minimalism also means the
architecture in this repo comes from this repo, not from framework convention.

## Consequences

- Request and response schemas are hand-written (Marshmallow or Pydantic standalone).
- `docs/api.md` is maintained by hand; contract tests enforce that code matches it.
- Long-running work must go to workers — there is no async escape hatch.
- Application factory and blueprint structure keep the app testable.

## Revisit if

A requirement appears for many concurrent long-lived connections — streaming LLM
responses to many simultaneous users, or websockets for live updates — where async would
materially change the deployment footprint.

## Action items

1. [ ] Application factory with blueprint registration per API version.
2. [ ] Pick the schema library and use it consistently.
3. [ ] Add contract tests asserting responses match `docs/api.md`.

---

# ADR-005: Hypothetical state is isolated from real state

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

The scenario simulator is the product's core feature. A user models a R350,000 vehicle
purchase and sees the effect on cash flow, debt ratio, savings trajectory, and net worth.

The hard requirement is that simulating must never alter the user's actual financial
record. A user who explores five scenarios and finds their real balances changed has lost
trust permanently. Scenarios must also be re-runnable with altered assumptions and
comparable against each other.

## Decision

Scenarios live in their own tables and never write to real financial tables. A scenario
stores its assumptions plus a reference to a snapshot of the user's position at creation
time. Running a scenario produces a `ScenarioResult` row containing the projection and the
inputs that produced it.

Applying a scenario to real state is a separate, explicit, audited operation with its own
endpoint and confirmation — not a side effect of running one.

## Options considered

### Option A: Separate tables with a position snapshot

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Isolation guarantee | Structural |
| Re-runnability | Straightforward |
| Storage | Duplicates a position snapshot per scenario |

**Pros:** contamination is structurally impossible, not merely avoided by care; results
are reproducible because inputs are frozen; comparison across scenarios is natural;
applying is explicit.
**Cons:** snapshot storage; a scenario created months ago is based on an old position and
the UI must say so.

### Option B: `is_hypothetical` flag on real tables

| Dimension | Assessment |
|---|---|
| Complexity | Low to write, high to live with |
| Isolation guarantee | Depends on every query filtering correctly |
| Re-runnability | Awkward |
| Storage | Minimal |

**Pros:** no duplication, reuses existing models.
**Cons:** one forgotten `WHERE is_hypothetical = false` puts imaginary money in a real
balance. That query will eventually be written. The guarantee rests on perpetual
vigilance.

### Option C: Copy-on-write branch of the user's whole financial state

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Isolation guarantee | Structural |
| Re-runnability | Excellent |
| Storage | Heaviest |

**Pros:** scenarios can be arbitrarily deep, including nested hypotheticals; merging back
is a well-defined operation.
**Cons:** substantial machinery for a feature whose scenarios are shallow; effectively
building version control for financial records.

## Trade-off analysis

Option B trades a structural guarantee for a procedural one on precisely the requirement
that most needs to be structural. Its low cost is illusory — it converts a one-time
schema decision into a permanent review burden on every future query.

Option C solves a problem the product does not have. Scenarios are one or two levels
deep, not branching trees.

Option A's cost is snapshot storage, which is small, and snapshot staleness, which is
solved by displaying the snapshot date and offering a re-baseline.

## Consequences

- Scenario tables: `scenarios`, `scenario_assumptions`, `scenario_results`,
  `position_snapshots`.
- Domain engines take a position value object as an argument and have no notion of whether
  it came from real or snapshot data — the same code serves both paths.
- The UI must display the snapshot date and offer re-baselining against current position.
- Applying a scenario is a distinct endpoint that writes real records and logs an audit
  entry.
- Snapshot rows need a retention policy.

## Revisit if

Users need nested or branching scenarios, which would push toward Option C.

## Action items

1. [ ] Model the scenario tables in `docs/database.md`.
2. [ ] Define the `FinancialPosition` value object shared by real and snapshot paths.
3. [ ] Add a test asserting a scenario run issues no writes to real financial tables.
4. [ ] Specify the apply-scenario flow and its audit record in `specs/scenarios.md`.

---

# ADR-006: Server state is a query cache, with no global client store

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

Almost everything the frontend displays originates on the server. ADR-003 makes this
unusually strong: forecasts, health assessments, risk flags, and the position snapshot are
all materialised by workers and persisted, so the API returns stored results rather than
derivations computed per request.

The client therefore has very little state of its own. What it has is a cache of server
responses, plus transient interface state — a form's contents, which tab is selected,
whether a disclosure is open.

Frontend state management is the decision most likely to be made by habit rather than by
argument, and the wrong choice adds a second source of truth to a product whose entire
claim is that there is exactly one.

## Decision

Server state is owned by TanStack Query, keyed to mirror the API's resource structure.
Interface state lives in the component that owns it, via `useState` or `useReducer`.

There is no global client store. Introducing one requires a new ADR.

## Options considered

### Option A: Query cache only

| Dimension | Assessment |
|---|---|
| Complexity | Low — one concept, no store to design |
| Fit to ADR-003 | Direct — the cache mirrors materialised server results |
| Risk of divergence | Minimal; there is no second copy to drift |
| Boilerplate | Low |

**Pros:** the cache is a cache of the truth rather than a parallel model of it; request
deduplication, background refetch, and staleness are already the library's vocabulary,
which matches ADR-003's staleness contract; nothing has to be kept in sync by hand.
**Cons:** genuinely cross-cutting interface state has no obvious home and gets passed
through props or context.

### Option B: Query cache plus a global store

| Dimension | Assessment |
|---|---|
| Complexity | Medium — two systems and a boundary between them |
| Fit to ADR-003 | Indirect — server data is copied into the store |
| Risk of divergence | Real; two copies of the same figure |
| Boilerplate | Medium |

**Pros:** a familiar home for cross-cutting state; convenient selectors.
**Cons:** the boundary erodes. Server figures get copied into the store "just for this
screen", and a product where a figure can be stale in two different ways has lost the
property this architecture exists to protect.

### Option C: Global store only

| Dimension | Assessment |
|---|---|
| Complexity | High — caching, deduplication, invalidation hand-written |
| Fit to ADR-003 | Poor |
| Risk of divergence | High |
| Boilerplate | High |

**Pros:** one mental model; no library-specific idioms.
**Cons:** reimplements a query cache, worse, and puts server figures in mutable client
state where they can be written.

## Trade-off analysis

Option C rebuilds a solved problem and reintroduces the risk that a financial figure is
mutable on the client.

Option A versus B turns on what happens over time rather than on what is convenient now.
Option B's store starts as a home for interface state and ends as a home for server data,
because the path of least resistance always runs that way. In a product whose central
claim is that every figure is traceable to the engine that computed it, a second mutable
copy on the client is precisely the wrong affordance to leave lying around.

Option A's real cost — that cross-cutting interface state is awkward — is small, and the
cases are few enough to handle with context where they arise.

## Consequences

- Query keys mirror API resources: `['position']`, `['scenarios', id, 'results']`.
- Mutations invalidate only what their endpoint's write affects. Running a scenario does
  not invalidate `['position']`, per ADR-005.
- The library's `staleTime` is an interface concern and is unrelated to ADR-003's
  `is_stale`, which is a property of the stored forecast. Conflating the two would be a
  bug; the naming collision is worth a comment where they appear together.
- Cross-cutting interface state uses context, deliberately and rarely.

## Revisit if

Genuine offline support or optimistic editing of financial records appears, either of
which would require a client-side model of state rather than a cache of server responses.

## Action items

1. [ ] Define the query-key convention in `docs/frontend.md`.
2. [ ] Add a lint rule forbidding imports of `api/` from `components/`.
3. [ ] Document the `staleTime` versus `is_stale` distinction where both are used.

---

# ADR-007: Follow the system appearance, with a three-state override

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

The interface supports a light and a dark appearance. Apple's guidance is unambiguous that
an app should not offer its own appearance setting — `dark-mode.md › Best practices`:
"Avoid offering an app-specific appearance setting. An app-specific appearance mode option
creates more work for people because they have to adjust more than one setting."

That guidance assumes a native app on a device whose owner controls the system setting. On
the web it collides with a real constraint: `prefers-color-scheme` reports the browser's
resolved preference, and on managed, shared, or locked-down machines the reader frequently
cannot change it. Users of this product are likely to be reading financial figures on a
work machine.

## Decision

The interface follows `prefers-color-scheme` by default.

A three-state control — System, Light, Dark — defaulting to System, is available in
settings. It is not present in the main interface.

## Options considered

### Option A: Three-state override, defaulting to System

| Dimension | Assessment |
|---|---|
| Complexity | Low — tokens already carry both appearances |
| Respects system preference | Yes, by default |
| Serves readers who cannot change the system setting | Yes |

**Pros:** honours the guidance for everyone who has a working system preference, while not
stranding those who do not; the default keeps the interface consistent with the rest of the
reader's environment.
**Cons:** a setting exists that Apple's guidance would prefer did not.

### Option B: System appearance only

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Respects system preference | Strictly |
| Serves readers who cannot change the system setting | No |

**Pros:** exactly what the guidance asks for; nothing to build or test.
**Cons:** a reader on a managed machine set to light who needs dark has no recourse, in a
product they may read for long stretches.

### Option C: Two-state toggle, defaulting to the system's current value

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Respects system preference | Only at first load |
| Serves readers who cannot change the system setting | Yes |

**Pros:** the familiar pattern; one control.
**Cons:** it cannot represent "follow the system", so it stops tracking the reader's
preference the moment it is touched — including the automatic light-to-dark switch through
the day that `dark-mode.md › Best practices` expects to keep working.

## Trade-off analysis

Option B is correct on a platform where the guidance's assumption holds, and this is not
quite that platform.

Option C is the common web pattern and is subtly worse than it looks: by having no System
state it converts a preference that tracks the environment into a fixed choice, which is
the actual harm the guidance is warning about.

Option A keeps the system preference authoritative by default and adds an escape hatch for
a constraint the guidance did not contemplate. The cost is one control in settings, which
is exactly where Apple places this kind of option anyway — `settings.md › Best practices`:
"Put general, infrequently changed settings in your custom settings area", with "interface
style" given as the example.

## Consequences

- Appearance resolves as: explicit override if set, otherwise `prefers-color-scheme`.
- The override persists per reader and must not cause a flash of the wrong appearance on
  load.
- Both appearances are tested, including under increased contrast, per
  `docs/design-system.md` §11.
- There is no appearance control in the main interface.

## Revisit if

Usage shows the override is essentially unused, in which case Option B is simpler and the
control can be removed.

## Action items

1. [ ] Resolve appearance before first paint to avoid a flash.
2. [ ] Add the control to settings, not to the main interface.
3. [ ] Add a visual test covering both appearances at increased contrast.

---

# ADR-008: Implementation-level libraries for the backend Foundation

**Status:** Accepted
**Date:** 2026-09-14
**Deciders:** Project owner

## Context

`docs/architecture.md` §5 requires an entry here for any new dependency. ADR-004 already
settled the framework (Flask) and the top-level stack table in `README.md` already names
SQLAlchemy, Alembic, PostgreSQL, and Redis + RQ. What remained unrecorded were the smaller
libraries the Foundation slice needs to satisfy requirements stated elsewhere in these
docs, each of which is otherwise unremarkable enough to slip in without a record — which is
exactly the case this rule exists for.

## Decision

The backend Foundation adds:

- **argon2-cffi** — `docs/database.md` names `password_hash` as `argon2id`; this is the
  reference argon2 binding for Python.
- **Flask-SQLAlchemy** / **Flask-Migrate** — thin Flask integration over SQLAlchemy/Alembic,
  which are already decided; adopted rather than wiring the engine and migration context
  by hand.
- **Flask-Limiter** — `docs/api.md`'s rate-limit table (login, assistant, scenario run,
  import, general) needs an enforcement point; this is the standard Flask rate limiter.
- **psycopg 3** — the PostgreSQL driver SQLAlchemy needs; psycopg 3 over psycopg2 because
  it is the actively developed line and ships a binary wheel for local development.
- **gunicorn** — the WSGI server the Dockerfile runs; not part of the request-time
  architecture, only how the process starts.

## Consequences

- These are implementation detail, not architecture: none of them appear in
  `docs/architecture.md`'s layer contracts, and swapping any one for an equivalent (a
  different rate limiter, a different WSGI server) does not require revisiting this ADR,
  only replacing the entry above.
- `requirements.txt` is the enforcement mechanism — a new backend dependency not listed
  there and not recorded here is a review finding.

## Revisit if

A library here is replaced, or a new one is added — update this record in the same pull
request, per `docs/architecture.md` §5.
