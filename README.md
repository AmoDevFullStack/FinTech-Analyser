# Financial Digital Twin

[![CI](https://github.com/AmoDevFullStack/FinTech-Analyser/actions/workflows/ci.yml/badge.svg)](https://github.com/AmoDevFullStack/FinTech-Analyser/actions/workflows/ci.yml)
[![CD](https://github.com/AmoDevFullStack/FinTech-Analyser/actions/workflows/cd.yml/badge.svg)](https://github.com/AmoDevFullStack/FinTech-Analyser/actions/workflows/cd.yml)

A financial decision platform that builds a model of your financial life and simulates what
happens to it when you make a decision.

Budgeting apps answer "here is what happened to your money." This answers "here is what
happens if you buy the car."

> The repository is named **FinTech-Analyser**; the product is the **Financial Digital Twin**.
> They are the same thing.

---

## Contents

- [The idea](#the-idea)
- [Status](#status)
- [Stack](#stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Development](#development)
- [Rules worth knowing before you touch anything](#rules-worth-knowing-before-you-touch-anything)
- [Documentation map](#documentation-map)
- [Project layout](#project-layout)
- [CI/CD and deployment](#cicd-and-deployment)
- [Troubleshooting](#troubleshooting)
- [Not financial advice](#not-financial-advice)

---

## The idea

Most personal finance software is a rear-view mirror. It categorises what you already spent
and shows it back to you in a pie chart. That is useful roughly once, because the decision
that mattered was made before the transaction appeared.

This system maintains a continuously updated model of income, spending behaviour, debt,
assets, savings, and commitments — the digital twin — and lets you run a hypothetical against
it. Buy a R350,000 vehicle at 11.75% over 72 months, with insurance and fuel, and you see the
effect on monthly cash flow, debt-to-income ratio, emergency fund coverage, savings
trajectory, and net worth at 60 months, against the do-nothing baseline.

The figures are computed by deterministic Python. The language model explains them and never
produces them. That boundary is the product.

---

## Status

**Built.** Both the "Now" and "Next" sections of [`PLAN.md`](PLAN.md):

- Foundation, and the financial core engines.
- CSV import across seven bank formats.
- All seven scenario types.
- Debts, goals, and financial health.
- Risk detection.
- Behavioural forecasting with accuracy measurement.
- Recommendations, and the AI CFO.
- A frontend for all of the above.

**Specified, deliberately not built:**

- Scenario `apply` (writing a scenario to real financial state).
- The queued 202 path for forecast refresh.
- Everything in `PLAN.md`'s "Later" section.

**Known gaps.** `PLAN.md` lists the known gaps in what *is* built. Read it before trusting a
figure in production. Five of the seven bank CSV detectors are built from documented column
names and have not been validated against real exports.

**Tested.** Every pull request runs:

- the full backend suite (560+ tests) against PostgreSQL 16, database-backed tests included;
- a migration upgrade/downgrade round-trip;
- the frontend suite;
- the tests for the deploy tooling;
- a Terraform validation.

The Playwright journey runs too, but does not block a merge until it has passed once.

`docs/` and `specs/` remain the source of truth the code was built against.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind, TanStack Query |
| Backend | Python 3.12, Flask, SQLAlchemy 2, Alembic, Pydantic |
| Database | PostgreSQL 16 |
| Queue | Redis 7 + RQ |
| Narration | OpenAI (optional; the app works without it) |
| Testing | pytest, Hypothesis, Vitest, Testing Library, Playwright, moto |
| Local stack | Docker Compose, Nginx |
| Production | AWS af-south-1: EC2, RDS, ECR, SSM, S3; Caddy for TLS; Terraform |
| CI/CD | GitHub Actions, OIDC to AWS, Dependabot |

---

## Quick start

You need **Docker** with the Compose plugin. Nothing else has to be installed to run the app.

```bash
git clone https://github.com/AmoDevFullStack/FinTech-Analyser.git
cd FinTech-Analyser
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend flask --app wsgi seed demo
```

With `make`, the last three lines are `make up migrate seed`.

| What | Where |
|---|---|
| App (Vite dev server, hot reload) | http://localhost:5173 |
| App behind Nginx, as routed in production | http://localhost |
| API | http://localhost:8000/api/v1 |
| API health / readiness / build | `/api/v1/health`, `/api/v1/ready`, `/api/v1/version` |

The demo seed creates a user with eighteen months of plausible transaction history, three
debts, and two goals — enough for the forecasting and analysis engines to produce meaningful
output. Log in with:

```
demo@financialdigitaltwin.local
demo-password-change-me
```

The seed prints these too. It is for local and staging use only.

---

## Configuration

Settings come from environment variables, read once at startup in
[`backend/app/core/config.py`](backend/app/core/config.py). Locally they come from `.env`; on
AWS they come from SSM Parameter Store (see [`docs/deployment.md`](docs/deployment.md)).

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | yes | Signs session cookies |
| `DATABASE_URL` | yes | PostgreSQL connection |
| `TEST_DATABASE_URL` | for tests | Must name a database ending in `_test`; the suite drops its tables |
| `REDIS_URL` | yes | Queue, and rate-limit counters shared across workers |
| `JWT_SECRET_KEY` | no | Signs bearer tokens; falls back to `SECRET_KEY`, but a separate key is better |
| `JWT_ACCESS_TTL_SECONDS` / `JWT_REFRESH_TTL_SECONDS` | no | Token lifetimes (15 minutes / 30 days) |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS` | no | Narration. Without a key, answers come back unnarrated with `narration_available: false` |
| `TRUSTED_PROXY_COUNT` | production | Reverse proxies in front of gunicorn (2 behind Caddy and Nginx); keys the login rate limit on the real client |
| `FLASK_ENV` | no | `development` locally. Anything else marks session cookies `Secure` |

The full list with comments is in [`.env.example`](.env.example). Never commit `.env`.

---

## Development

### Everyday commands

Run `make` on its own to list every target. The common ones:

| Command | Does |
|---|---|
| `make up` / `make down` | Start / stop the local stack |
| `make migrate` / `make seed` | Apply migrations / create the demo user |
| `make fix` | Auto-fix formatting and lint (ruff, eslint) |
| `make check` | Every CI check that needs no database: lint, format, no-float rule, mypy, tsc |
| `make test` | Backend and frontend suites, inside the stack |
| `make test-domain` | The financial engines only; fast |
| `make e2e` | Playwright against the running stack (seed first) |
| `make clean` | Delete caches and build output; keeps `.env` and `node_modules` |

`make fix` and `make check` run on your machine. For them you need Python 3.12 with
`pip install -r backend/requirements-dev.txt`, and Node 22 with `npm ci` in `frontend/`. The
test targets run inside Docker, because the backend suite needs Postgres.

### Tests without make

```bash
docker compose exec backend pytest                    # backend, all
docker compose exec backend pytest tests/domain -q    # engines only, fast
docker compose run --rm frontend npm test -- --run    # frontend
docker compose run --rm playwright                    # end to end (needs the demo seed)
```

### Contributing a change

1. Branch from `main`.
2. Make the change, then run `make fix` and `make check`.
3. Open a pull request. CI must be green before it can merge.
4. A database change is a new Alembic revision in `backend/migrations/versions/`, and it
   needs a working `downgrade()`. Follow the expand/contract rules in
   [`docs/deployment.md`](docs/deployment.md) §6, so the previous release can still run
   against the new schema.
5. Feature work starts from its spec in `specs/`. Calculation code follows ADR-001 and
   `docs/architecture.md` §5.

Contributors should read `docs/architecture.md` and
`docs/decisions.md` before your first change, and the relevant file in `specs/` before
implementing a feature.

---

## Rules worth knowing before you touch anything

**Money is `Decimal` in Python and `NUMERIC(15, 2)` in Postgres.** Never a float, never a
JSON number. This is not a preference: projections compound over 60 periods, and
representation error accumulates into figures a user would be right to distrust. CI fails any
`float(` in `app/domain/`. See ADR-001.

**The language model never computes a figure.** It receives a computed result and turns it
into language. See ADR-002.

**Scenarios never write to real financial state.** Isolation is structural, not procedural.
See ADR-005.

**The frontend performs no financial calculations.** If a number is on screen, the API
supplied it.

**Every financial query is scoped to the authenticated user at the repository layer.**

---

## Documentation map

| Question | File |
|---|---|
| What must the system do? | [`docs/requirements.md`](docs/requirements.md) |
| How is the code organised, and what may each layer contain? | [`docs/architecture.md`](docs/architecture.md) |
| Why was it built this way, and what may I not change? | [`docs/decisions.md`](docs/decisions.md) |
| How is data modelled? | [`docs/database.md`](docs/database.md) |
| What is the HTTP contract? | [`docs/api.md`](docs/api.md) |
| How is the frontend organised? | [`docs/frontend.md`](docs/frontend.md) |
| What should it look like, and why? | [`docs/design-system.md`](docs/design-system.md) |
| How does a specific feature behave? | [`specs/<feature>.md`](specs/) |
| What are we building next, and what are the known gaps? | [`PLAN.md`](PLAN.md) |
| How does code reach production, and how do I set up AWS? | [`docs/deployment.md`](docs/deployment.md) |

---

## Project layout

```
FinTech-Analyser/
├── backend/
│   ├── app/
│   │   ├── api/            HTTP layer (blueprints under api/v1/)
│   │   ├── services/       application services
│   │   ├── domain/         deterministic financial engines — no I/O, no floats
│   │   ├── repositories/   every query, scoped to the user
│   │   ├── models/         SQLAlchemy models
│   │   ├── schemas/        request and response validation
│   │   ├── workers/        RQ jobs
│   │   ├── llm/            intent layer and narration provider
│   │   └── core/           config, auth, money, events, release/readiness
│   ├── migrations/         Alembic revisions
│   └── tests/
├── frontend/
│   ├── src/                pages, features, components, API client
│   ├── e2e/                Playwright
│   └── nginx.conf          production web server (baked into the image)
├── infrastructure/
│   ├── caddy/              TLS termination in production
│   ├── docker/             local Postgres init (creates the _test database)
│   ├── nginx/              local routing
│   └── terraform/          AWS: bootstrap, global, modules/environment, envs/*
├── scripts/                aws_deploy.py, remote-deploy.sh, smoke_test.py (+ tests)
├── docs/                   architecture, requirements, database, API, decisions, deployment
├── specs/                  per-feature behavioural contracts
├── .github/                CI, CD, reusable deploy, Dependabot
├── docker-compose.yml       local stack
├── docker-compose.prod.yml  staging and production hosts, from ECR images
├── Makefile
├── .env.example
└── PLAN.md
```

---

## CI/CD and deployment

**On every pull request** ([`ci.yml`](.github/workflows/ci.yml)):

- **Backend:** lint, format, the no-float rule, and mypy. Then the test suite against
  PostgreSQL 16, with a coverage gate on the financial engines.
- **Migrations:** a round-trip — upgrade, downgrade to base, upgrade again.
- **Frontend:** lint, types, tests, and a production build.
- **Images:** both production images are built.
- **Deploy tooling:** tested against mocked AWS.
- **Terraform:** `terraform validate` on every stack.
- **Playwright:** the end-to-end journey.

**On merge to `main`** ([`cd.yml`](.github/workflows/cd.yml)), images are pushed to ECR,
tagged with the commit SHA. That commit is then deployed to **staging**.

**On a `vX.Y.Z` tag**, the same images are promoted to **production** without rebuilding,
after a required reviewer approves:

```bash
git tag -a v1.2.0 -m "v1.2.0" && git push origin v1.2.0
```

Every deploy:

1. Snapshots the RDS database.
2. Renders the host's configuration from SSM Parameter Store.
3. Runs migrations. If they fail, nothing new starts.
4. Replaces the containers.
5. Smoke-tests the live URL. `/api/v1/ready` must report the schema at this build's
   migration head, and `/api/v1/version` must report the deployed commit.

If step 4 or 5 fails, the containers roll back automatically. To roll back by hand, run the
CD workflow with an earlier SHA.

**Infrastructure.** Each environment is one EC2 host running the containers, with PostgreSQL
on RDS in private subnets. There is no SSH: deploys and shell access go through SSM. GitHub
reaches AWS with OIDC, so no AWS keys are stored in GitHub. It is all Terraform, in
[`infrastructure/terraform/`](infrastructure/terraform/).

Setting AWS up from an empty account, costs, operations, database restores, and the release
checklist are in [`docs/deployment.md`](docs/deployment.md). Until the AWS variables are set
in GitHub, CD does nothing and CI runs as usual.

---

## Troubleshooting

**`Refusing to run the test suite against database 'fdt'`.** This is the test suite
protecting your development data. `TEST_DATABASE_URL` must name a database ending in
`_test`. A fresh stack creates `fdt_test` automatically. On a stack created before that
existed, create it once:

```bash
docker compose exec postgres createdb -U fdt fdt_test
```

**Port 5173, 8000 or 80 is already in use.** Stop whatever holds it, or change the host side
of that port mapping in `docker-compose.yml`. Postgres and Redis publish no host ports, so a
local install of either does not conflict.

**Logged in, but bounced straight back to the login page.** Session cookies are `Secure`
unless `FLASK_ENV=development`. Locally, check `.env`. On a deployed environment, make sure
you are on HTTPS: Caddy needs `APP_DOMAIN` set and DNS pointing at the host.

**`/api/v1/ready` returns 503.** Look at the JSON:
- `"database": false` means Postgres is unreachable.
- `"schema_current": false` means migrations have not been applied. Run `make migrate`
  locally, or check the deploy log on AWS.

**The assistant answers without explanations.** No `OPENAI_API_KEY` is set. That is
supported: the figures are complete without narration.

**Too many login attempts (HTTP 429).** The limit is 5 attempts per 15 minutes per client
address. If everyone is limited at once on a deployed environment, `TRUSTED_PROXY_COUNT` is
not set to the number of proxies in front of the app.

---

## Not financial advice

This software produces projections from assumptions. Projections are not predictions, and
nothing it outputs is financial advice. Assumptions are always visible and editable precisely
so that you can disagree with them.
