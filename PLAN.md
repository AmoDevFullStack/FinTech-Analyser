# Plan

What gets built, in what order, and why that order.

`docs/requirements.md` says what the system must do. This file says which parts happen
when. Where the two disagree, requirements win and this file is out of date.

---

## Sequencing principle

Build the vertical slice before the breadth. One account, one import, one scenario, one
projection, end to end and trustworthy, beats eleven half-built capabilities.

The reason is specific to this product: every feature depends on the domain engines being
correct, and correctness is only demonstrable end to end. A dashboard built before the
engines are trustworthy is a dashboard displaying figures nobody has validated.

---

## Now

The thinnest path that proves the thesis.

**Foundation**
- Flask application factory, blueprint structure, configuration, error envelope
- PostgreSQL schema and Alembic migrations for users, accounts, transactions, categories
- Authentication with session cookies, rate limiting, password reset
- Docker Compose: backend, frontend, Postgres, Redis, Nginx
- Money helpers and the `Decimal` boundary, per ADR-001
- CI: pytest, the no-float check on `app/domain/`, lint, type check

**Financial core**
- `domain/amortisation.py` with reference-figure tests
- `domain/cash_flow.py`, `domain/net_worth.py`, `domain/emergency_fund.py`
- Reference spreadsheet model producing the expected values these tests assert against

**Data in**
- CSV import: format detection for two banks, staging, exact deduplication, commit, undo
- Rules-based categorisation with user correction
- Transfer detection
- Derived balances

**Proof of thesis**
- Position snapshot
- Vehicle purchase scenario, end to end: create, run, compare to baseline, save, re-run
- Forecast worker producing 60-month projections
- Dashboard reading stored results

**Quality gate before anything moves to Next**
- Domain coverage above 95%
- Repository tests proving user scoping
- A test asserting a scenario run writes nothing to real tables
- Playwright covering import through scenario result

---

## Next

Breadth on a foundation that has been proven.

- Remaining bank CSV formats, probable-duplicate conflict resolution, column mapping
- Similarity-based categorisation learning from corrections
- Recurrence detection
- Debts: full schedules, strategy comparison, what-if
- Goals: progress, achievability, competition
- Financial health engine with component breakdown
- Risk detection, all six types
- Remaining scenario types
- Forecast accuracy measurement
- AI CFO: intent classification, context assembly, narration, unsupported path
- Recommendations engine
- Frontend build-out against the design system

---

## Later

- Bank aggregator integration behind the existing interface
- Credit bureau integration, per `specs/credit.md`
- Monte Carlo projection producing ranges rather than point estimates
- Household and multi-user support
- Mobile
- Terraform environments and production deployment
- Data export and account deletion at production quality

---

## What moved to Later to make Now fit

Stated explicitly, because scope decisions that are not recorded get relitigated:

Live bank connections, credit data, all scenario types beyond vehicle purchase, the AI
layer, recommendations, and risk detection. Each is in the architecture and none is in the
first slice. The AI layer in particular is the most visible feature and the least
load-bearing — it narrates figures that must already be correct, so it cannot sensibly
precede them.

---

## Sprint 1

Two weeks, one developer, roughly 50 productive hours after meetings.

**Goal:** a user can register, create an account, import a CSV, and see a derived balance
and a categorised transaction list.

**P0** — foundation, schema, auth, one bank's CSV import with exact deduplication,
rules-based categorisation, derived balances, transaction list UI, CI pipeline.

**Stretch** — second bank format, transfer detection, category correction UI.

**Not this sprint** — scenarios, forecasting, dashboard, anything AI.

**Risk:** CSV format variation is the classic underestimate. If format detection consumes
more than a day, fall back to manual column mapping for sprint 1 and defer detection.

## Sprint 2

**Goal:** the vertical slice closes. A user with imported transactions can run a vehicle
purchase scenario and see its impact against baseline.

**P0** — amortisation engine with reference tests, position snapshot, scenario create and
run, baseline comparison, result persistence, scenario UI, the no-writes-to-real-tables
test.

**Stretch** — forecast worker, dashboard.

The reference spreadsheet model is a prerequisite for the amortisation engine, not a
parallel task. Expected values come first.

---

## Metrics

Instrumented from sprint 3, not before — metrics on a product nobody uses measure nothing.

**Thesis metrics**, which tell us whether the product works: scenarios created per active
user, proportion of users running a scenario more than once, forecast accuracy against
realised actuals, and risk flags acknowledged before the projected date.

**Health metrics**: import success rate, categorisation accuracy after correction, dashboard
server time, forecast generation duration.

**Engagement metrics**: weekly active users, sessions per user, time to first scenario.

The metric that matters most is forecast accuracy, because it is the only one that measures
whether the projections deserve to be believed. Everything else measures whether people are
using something that may or may not be right.

---

## Risks

**Bank CSV variation.** Highest-probability schedule risk. Mitigated by manual column
mapping as a permanent fallback.

**Categorisation quality.** Bad categorisation corrupts every downstream figure. Mitigated
by making correction trivial and by never overwriting a correction.

**Determinism drift.** A refactor that changes an engine's output invalidates stored
results silently. Mitigated by engine versioning on every stored result and reference-figure
tests that fail loudly.

**Scope pull toward the AI layer.** It demos well and depends on everything else being
correct. Mitigated by its position in Next, and by this paragraph existing.
