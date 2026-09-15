# Financial Digital Twin

A financial decision platform that builds a model of your financial life and simulates what
happens to it when you make a decision.

Budgeting apps answer "here is what happened to your money." This answers "here is what
happens if you buy the car."

---

## The idea

Most personal finance software is a rear-view mirror. It categorises what you already
spent and shows it back to you in a pie chart. That is useful roughly once, because the
decision that mattered was made before the transaction appeared.

This system maintains a continuously updated model of income, spending behaviour, debt,
assets, savings, and commitments — the digital twin — and lets you run a hypothetical
against it. Buy a R350,000 vehicle at 11.75% over 72 months, with insurance and fuel, and
you see the effect on monthly cash flow, debt-to-income ratio, emergency fund coverage,
savings trajectory, and net worth at 60 months, against the do-nothing baseline.

The figures are computed by deterministic Python. The language model explains them and
never produces them. That boundary is the product.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind |
| Backend | Python, Flask, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Queue | Redis + RQ |
| Testing | pytest, Hypothesis, Vitest, Playwright |
| Infrastructure | Docker, Docker Compose, Nginx, Terraform |

---

## Quick start

Requires Docker and Docker Compose.

```bash
git clone <repo> && cd financial-digital-twin
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli seed --demo
```

Frontend on `http://localhost:5173`, API on `http://localhost:8000/api/v1`.

The demo seed creates a user with eighteen months of plausible transaction history, three
debts, and two goals — enough for the forecasting and analysis engines to produce
meaningful output. Credentials are printed by the seed command.

Running the tests:

```bash
docker compose exec backend pytest                    # backend
docker compose exec backend pytest app/domain -q      # engines only, fast
docker compose run --rm frontend npm test             # frontend
docker compose run --rm playwright npx playwright test
```

---

## Which document to read

| Question | File |
|---|---|
| What must the system do? | `docs/requirements.md` |
| How is the code organised, and what may each layer contain? | `docs/architecture.md` |
| Why was it built this way, and what may I not change? | `docs/decisions.md` |
| How is data modelled? | `docs/database.md` |
| What is the HTTP contract? | `docs/api.md` |
| How is the frontend organised? | `docs/frontend.md` |
| What should it look like, and why? | `docs/design-system.md` |
| How does a specific feature behave? | `specs/<feature>.md` |
| What are we building next? | `PLAN.md` |

If you are an AI coding agent working in this repository, read `docs/architecture.md` and
`docs/decisions.md` before your first change, and the relevant file in `specs/` before
implementing a feature. The repository also carries a
`.claude/skills/financial-domain-engine/` skill covering the conventions for calculation
code specifically.

---

## Rules worth knowing before you touch anything

Money is `Decimal` in Python and `NUMERIC(15, 2)` in Postgres. Never a float, never a JSON
number. This is not a preference — projections compound over 60 periods and representation
error accumulates into figures a user would be right to distrust. See ADR-001.

The language model never computes a figure. It receives a computed result and turns it into
language. See ADR-002.

Scenarios never write to real financial state. Isolation is structural, not procedural. See
ADR-005.

The frontend performs no financial calculations. If a number is on screen, the API supplied
it.

Every financial query is scoped to the authenticated user at the repository layer.

---

## Project layout

```
financial-digital-twin/
├── docs/               architecture, requirements, database, API, decisions
├── specs/              per-feature behavioural contracts
├── backend/
│   └── app/
│       ├── api/        HTTP layer
│       ├── services/   application services
│       ├── domain/     deterministic financial engines
│       ├── repositories/
│       ├── models/
│       ├── workers/
│       ├── llm/
│       ├── integrations/
│       └── core/
├── frontend/src/
├── infrastructure/
│   ├── docker/
│   ├── nginx/
│   └── terraform/
├── .claude/skills/     project-specific agent skills
├── docker-compose.yml
├── .env.example
├── PLAN.md
└── README.md
```

---

## Status

Both the "Now" and "Next" sections of `PLAN.md` are built: Foundation, the financial
core engines, CSV import across seven bank formats, all seven scenario types, debts,
goals, financial health, risk detection, behavioural forecasting with accuracy
measurement, recommendations, the AI CFO, and the frontend for all of it.

Three things are specified and deliberately not built: scenario `apply` (writing a
scenario to real financial state), the queued 202 path for forecast refresh, and
everything in `PLAN.md`'s "Later" section. `PLAN.md` also lists the known gaps in what
*is* built — read that before trusting a figure in production.

One caveat worth stating plainly: the database-backed test suite has never run. No
Postgres was available in the environment this was built in, so the domain and unit
suites (220 tests) pass while every repository and service test errors on connection.
Run `docker compose exec backend pytest` before believing any of it works end to end.

`docs/` and `specs/` remain the source of truth the code was built against.

---

## Not financial advice

This software produces projections from assumptions. Projections are not predictions, and
nothing it outputs is financial advice. Assumptions are always visible and editable
precisely so that you can disagree with them.
