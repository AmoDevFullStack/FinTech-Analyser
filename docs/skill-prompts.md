# Skill prompt playbook — Financial Digital Twin

Every skill installed in this environment, mapped to where it earns its place in this
project, with a prompt you can paste as-is. Keep this file at `docs/skill-prompts.md`
so a coding agent can find the right entry point instead of guessing.

**How to use it**

- Prompts are written to trigger the skill on wording alone — no `/command` needed.
- Anything in `<angle brackets>` is a slot you fill in.
- Prompts assume the agent has already read `docs/architecture.md` and `docs/decisions.md`.
  Where that matters, the prompt says so explicitly.
- Order below follows the lifecycle: define → design → get the maths right → build →
  ship → operate.

---

## Phase 0 — Define the product

### `product-management:brainstorm` / `product-management:product-brainstorming`

Use before anything is written down. These are sparring partners, not document
generators — expect pushback.

> Brainstorm with me on the Financial Digital Twin. The thesis is that budgeting apps
> answer "here is what happened to your money" and nobody has built the thing that
> answers "here is what happens if I do this". Stress-test that. Who actually feels this
> pain badly enough to change tools, what's the wedge feature, and what's the most
> likely reason this becomes another dashboard nobody opens twice?

> Push back on my scoping. I have eleven capabilities listed — digital twin, command
> centre, scenario simulator, forecasting, time machine, AI CFO, health engine, debt
> intelligence, goals, risk detection. Which two are the product and which nine are
> features of those two? Argue for a position rather than listing trade-offs.

### `product-management:competitive-brief`

> Write a competitive brief for the personal financial simulation space. Cover
> 22seven, Monarch Money, Copilot Money, Origin, Projection Lab, and YNAB. Focus on
> which of them do forward projection versus backward reporting, how they handle
> hypothetical scenarios, and where a South African user is underserved. End with where
> we differentiate versus where we just need parity.

### `design:user-research`

> Write an interview guide for validating the scenario simulator. I want to learn how
> people currently reason about a large financial decision — a car, a move, a bond —
> before they commit. Eight to ten questions, non-leading, aimed at capturing the
> mental arithmetic they do today and where it fails them.

### `product-management:synthesize-research` / `design:research-synthesis`

Run whichever is available once you have raw notes. `synthesize-research` leans toward
roadmap output, `research-synthesis` toward themes and segments.

> Here are notes from <n> interviews about financial decision-making. Synthesise them
> into themes ranked by frequency and impact, identify distinct user segments, and tell
> me which findings should change the roadmap and which are noise.

### `product-management:write-spec`

The workhorse. One pass per file in `specs/`.

> Write the feature spec for the scenario simulator, targeted at `specs/scenarios.md`.
> Problem statement: a user wants to know the full downstream impact of a R350,000
> vehicle purchase before committing. Include goals, non-goals, inputs, processing flow,
> outputs, constraints (a scenario must never mutate real financial state), and
> acceptance criteria as checkboxes. Follow the layering in `docs/architecture.md` —
> the spec describes behaviour, not structure.

Repeat for: `transactions.md`, `accounts.md`, `debts.md`, `goals.md`, `forecasting.md`,
`financial-health.md`, `credit.md`, `recommendations.md`, `dashboard.md`.

### `product-management:roadmap-update`

> Build a Now / Next / Later roadmap from `specs/`. Now must be the thinnest slice that
> proves the thesis end to end — accounts, transactions, one scenario type, one
> projection. Tell me explicitly what moves to Later to make that fit.

---

## Phase 1 — Architecture and specification

### `engineering:system-design`

> Design the forecasting subsystem. Requirements: project cash flow, savings, debt
> balances, emergency fund and net worth up to 60 months out, from historical
> transactions plus user assumptions. Constraints: Python, deterministic, must be
> reproducible from stored inputs, too slow for a request cycle. Cover the service
> boundary, the data model for stored projections, invalidation rules when new
> transactions land, and the API shape.

### `engineering:architecture`

One ADR per decision in `docs/decisions.md`. These are the five that are expensive to
reverse.

> Write an ADR for representing money. Options: PostgreSQL `NUMERIC(15,2)` with Python
> `Decimal`, integer minor units, or float. Cover context, decision, consequences, and
> what would have to be true to revisit it.

> Write an ADR for the boundary between the deterministic financial engine and the LLM
> layer. The decision is that the LLM never computes a figure — it receives a computed
> result object and narrates it. Document the failure modes this prevents and the cost
> it imposes.

> Write an ADR for asynchronous forecast materialisation versus computing projections on
> request. Include the staleness contract we're accepting.

> Write an ADR for Flask over FastAPI or Django for this project, given the data-science
> integration requirement. Be honest about what we give up.

> Write an ADR for scenario isolation — hypothetical state in separate tables referencing
> a snapshot of real state, versus copy-on-write, versus an `is_hypothetical` flag.

### `engineering:documentation`

> Write `docs/architecture.md` as the source of truth for coding agents. It must define
> the layers (frontend, REST API, application services, domain engines, repositories,
> PostgreSQL), the dependency rules between them, what each layer must never contain,
> and the naming conventions for services and repositories. Written as instructions to
> an agent, not as prose for a human reader.

> Write the project README: what this is, the product thesis in two sentences, the stack,
> local setup with Docker Compose, and a map of which doc to read for what.

> Write `docs/database.md`. Entities, relationships, and the hard rules: every financial
> record is user-scoped, money is `NUMERIC` never float, `created_at` and `updated_at`
> everywhere, soft delete where historical integrity matters.

> Write `docs/api.md` as the REST contract under `/api/v1` — auth, accounts,
> transactions, debts, goals, scenarios, forecasts. Include request and response shapes
> and error envelopes. This file is authoritative; code follows it.

### `doc-coauthoring`

Better than `documentation` when you're still deciding what the doc should say.

> Co-author `docs/requirements.md` with me. Interview me for context first, then draft,
> then test it against the question "could a new agent implement from this without
> asking me anything?"

### `docs` (living docs tool)

> Put the requirements document in a doc I can share and keep editing, with a tab per
> capability area.

### `deep-research`

Only fires where a subagent/Task tool exists.

> Research how consumer financial planning tools model debt amortisation and net-worth
> projection. I need the standard formulas, the usual assumptions about inflation and
> salary growth, and how the serious tools handle uncertainty ranges rather than point
> estimates. Synthesise into something I can turn into domain-engine specs.

---

## Phase 2 — Financial correctness

This is the group most people skip, and it's where a finance app actually fails. The
`finance:*` skills encode accounting conventions your domain layer needs to respect.

### `financial-calculator`

The closest match to the domain engines themselves. Use it to derive and sanity-check
the maths before implementing.

> Work through the maths for a vehicle finance scenario: R350,000 price, R50,000 deposit,
> 11.75% annual interest, 72-month term, plus insurance, fuel and maintenance estimates.
> Show the amortisation, total interest, monthly cash-flow impact and debt-to-income
> shift. Show your work — I'm turning this into a deterministic Python engine and I need
> the reference figures for the test suite.

> Compare three debt repayment strategies — avalanche, snowball, and consolidation — on
> the same debt set. Give me the formulas and the crossover conditions, not just results.

### `finance:financial-statements`

> The Financial Command Centre needs a personal equivalent of the three statements —
> an income-and-expense view, a net-worth position, and a cash-flow view. Map the GAAP
> presentation conventions onto personal finance, tell me what carries over and what
> doesn't, and define the line items and period-comparison rules our domain layer should
> produce.

### `finance:variance-analysis`

Directly the Financial Time Machine and the forecast-accuracy loop.

> Design the variance engine: forecast versus actual on monthly cash flow, decomposed
> into drivers (income change, category-level spend change, one-off events, timing). Give
> me the decomposition methodology, sensible materiality thresholds for a personal budget,
> and the rules for generating narrative commentary the LLM layer can turn into prose.

### `finance:reconciliation`

The bank-import matching problem is a reconciliation problem.

> I'm building transaction import with deduplication — the same transaction can arrive
> from a CSV upload and later from an API feed. Apply reconciliation methodology: matching
> rules, tolerance windows, categorising unmatched items, aging, and what gets escalated
> to the user rather than auto-resolved.

### `finance:journal-entry` / `finance:journal-entry-prep`

> Our ledger needs double-entry discipline so balances always reconcile. Using journal
> entry conventions, define the entry types this app produces — transaction posted,
> transfer between accounts, debt repayment split into principal and interest, accrued
> interest, scenario applied to real state — with the debit and credit sides and the
> supporting detail each must carry.

### `finance:close-management`

> Design the monthly financial-position snapshot job as a close process: the ordered task
> list, dependencies between steps (import → categorise → reconcile → recompute balances
> → recompute health score → regenerate forecasts), and what blocks what if a step fails.

### `finance:audit-support` / `finance:sox-testing`

Repurposed as controls design — how you prove the engine is trustworthy.

> Treat the financial engine as a system under control testing. Define the key controls:
> every stored figure traceable to inputs, calculations reproducible from persisted
> assumptions, no LLM output written to a financial field, user-scoping enforced at the
> repository layer. For each control, describe the evidence it produces and how it would
> be tested.

---

## Phase 3 — Interface and design

### `frontend-design`

> Build the Financial Command Centre dashboard. React, TypeScript, Tailwind. Needs a
> current-position summary, cash-flow chart, upcoming obligations, financial-health
> score, and risk flags. Give it real aesthetic direction — this should not look like a
> generic admin template. No financial calculations in the frontend; it renders values
> the API supplies.

### `web-artifacts-builder`

> Build a clickable prototype of the scenario simulator as a multi-screen React artifact
> with shadcn/ui — assumptions form, before/after comparison, projected cash-flow and
> debt charts, impact summary. Mock data is fine; I want to feel the flow before
> committing to the API contract.

### `design:design-system`

> Extend our design system for financial data display. Define the patterns: monetary
> values (positive, negative, projected, hypothetical), confidence ranges on forecasts,
> risk severity levels, and before/after comparison. Include variants, states and
> accessibility notes for each.

### `design:design-critique`

> Critique this scenario simulator screen. The user is making a decision worth hundreds
> of thousands of rand — tell me where the hierarchy fails, where uncertainty is being
> presented as certainty, and what a stressed person would misread.

### `design:accessibility-review`

> Run a WCAG 2.1 AA audit on the dashboard. Particular attention to colour-only encoding
> of financial status — red for negative, green for positive — chart accessibility, and
> whether the whole scenario flow is keyboard-operable.

### `design:design-handoff`

> Generate the developer handoff spec for the scenario simulator: layout, design tokens,
> component props, interaction states, responsive breakpoints, loading and error states
> for a long-running projection, and edge cases like a scenario that makes cash flow
> negative.

### `design:ux-copy`

> Write the UX copy for the risk detection feature. Tone: direct, never alarmist, never
> shaming. Cover the alert titles for cash-flow shortfall, excessive debt exposure,
> unusual spending and insufficient reserves, plus the empty state before enough history
> exists, and the disclaimer that these are projections rather than advice.

> Review this error copy for the bank import flow. Every message should tell the user
> what happened, whether their data is safe, and what to do next.

### `theme-factory`

> Apply a theme to the dashboard prototype — something that reads as trustworthy and
> calm rather than fintech-neon. Show me two options before committing.

### `brand-guidelines`

> Apply consistent brand colours and typography across the dashboard, the marketing page
> and the exported PDF report so they read as one product.

### `canvas-design` / `paint` / `algorithmic-art` / `slack-gif-creator`

Peripheral, but real uses exist.

> Design a one-page visual explainer poster of the digital-twin concept for the repo
> README and landing page.

> Make a short animated GIF of the scenario before/after comparison for the team Slack
> when the simulator ships.

---

## Phase 4 — Build, test, ship

### `engineering:testing-strategy`

> Design the testing strategy. The critical property is that financial calculations are
> deterministic and reproducible. Cover: unit tests for domain engines using known
> reference figures, property-based tests for invariants (balances never drift, a
> scenario never mutates real state), integration tests for repositories with real
> Postgres, API contract tests, and Playwright coverage for the scenario flow. Tell me
> what the pyramid should look like and where not to bother.

### `engineering:code-review`

> Review this PR against `docs/architecture.md` and `docs/decisions.md`. Flag layer
> violations, any float used for money, any query not scoped to the authenticated user,
> N+1 queries, and any place an LLM response is written into a financial field. Python
> must use 3.12+ style annotations — `list[str]`, `X | None`, not `Optional` — and
> bound parameters rather than string-interpolated SQL.

### `engineering:debug`

> The 60-month forecast returns different figures on repeated runs with identical inputs.
> Deterministic output is a hard requirement. Reproduce, isolate, and diagnose.

### `engineering:tech-debt`

> Audit the backend for technical debt. Prioritise by risk to financial correctness
> first, then maintainability. I specifically want to know where business logic has
> leaked into route handlers or the frontend.

### `engineering:deploy-checklist`

> Pre-deployment checklist for the release that adds the scenarios tables. Includes an
> Alembic migration on live financial data, a feature flag on the simulator UI, and a new
> worker queue. Document rollback triggers before we ship, not after.

### `engineering:sprint-planning` *(via `product-management:sprint-planning`)*

> Plan the first sprint. Two weeks, one developer, roughly 50 hours after meetings. Goal
> is the vertical slice: account creation, transaction import, one scenario type, one
> projection. Tell me what's P0 and what's stretch.

### `engineering:standup`

> Generate my standup from yesterday's commits and ticket moves on the digital-twin repo.

### `product-management:metrics-review`

> Define the product metrics for this before we have any. What actually indicates the
> simulator is working — scenarios created per active user, scenario-to-decision
> conversion, forecast accuracy measured against later actuals? Then set up the monthly
> review format.

### `product-management:stakeholder-update`

> Write the monthly update on the digital-twin build in three versions: a five-line exec
> brief, an engineering-detail version, and one for early users.

### `engineering:incident-response`

> Forecast generation has been failing silently for 18 hours — users are seeing stale
> projections with no indication they're stale. Triage severity, draft the user
> communication, and after we resolve it, the blameless postmortem.

---

## Phase 5 — Tooling, automation, deliverables

### `skill-creator`

The highest-leverage entry in this file. Turn your own conventions into a skill so you
stop re-explaining them.

> Create a skill called `financial-domain-engine` that encodes how this project
> implements deterministic financial calculations: `Decimal` only, pure functions with no
> I/O, explicit rounding at boundaries, every engine paired with a reference-figure test,
> and the required docstring format documenting formula and assumptions. It should
> trigger whenever someone is writing or modifying code under `backend/app/domain/`.

> Create a skill called `spec-compliance` that makes an agent read `docs/architecture.md`,
> `docs/decisions.md` and the relevant file in `specs/` before touching code, and update
> the spec whenever behaviour changes.

### `cowork-plugin-management:create-cowork-plugin`

> Package the digital-twin conventions into an installable plugin: the
> `financial-domain-engine` and `spec-compliance` skills, a `/spec` command that scaffolds
> a new feature spec from the template, and a `/adr` command for decision records.

### `cowork-plugin-management:cowork-plugin-customizer`

> Customise the engineering plugin for this project — point code-review at
> `docs/decisions.md`, add the money-handling and user-scoping rules to its default
> checks, and set the testing-strategy defaults to pytest plus Playwright.

### `mcp-builder`

> Build an MCP server exposing the digital twin's read-only financial context — current
> position, account balances, active goals, latest forecast — so an agent can answer
> questions about my finances without direct database access. Python, FastMCP. Read-only
> by design: no tool may mutate financial state.

### `xlsx`

> Build a spreadsheet model of the debt intelligence engine — avalanche versus snowball
> versus consolidation across a sample debt set, with the amortisation schedules visible.
> I'll use it as the reference implementation to validate the Python engine against.

### `docx`

> Produce the technical design document as a Word file for the portfolio submission:
> architecture, data model, domain engine design, AI integration boundary, and testing
> approach, with a table of contents.

### `pptx`

> Build a 12-slide deck presenting this project: the problem, the thesis, the
> architecture, the AI boundary decision, a scenario walkthrough, and what I'd build next.

### `pdf`

> Generate the user-facing monthly financial report as a PDF from a sample result object
> — position summary, cash-flow chart, goal progress, risk flags.

### `file-reading` / `pdf-reading`

> Read the attached bank statement PDF and the transaction CSV export and tell me what
> fields the import parser has to handle, including the awkward ones — split
> descriptions, reversed transactions, fee lines.

### `google-workspace`

> Put the requirements document into a Google Doc and the roadmap into a Sheet so I can
> share both.

### `internal-comms`

> Write the project kickoff note and the launch announcement for the scenario simulator.

### `setup-writing-style`

> Learn my writing voice from these samples so the documentation and stakeholder updates
> sound like me rather than generic AI.

### `product-self-knowledge`

> The AI CFO layer calls the Claude API. Confirm the current model strings, tool-use
> mechanics, streaming, batch options and pricing before I write the integration — don't
> rely on memory for this.

### `learn`

> Teach me how Monte Carlo simulation applies to personal financial projection, from
> scratch. I want to understand it well enough to decide whether our forecasts should
> produce ranges rather than point estimates.

### `built-in-browser` / `chrome-browser` / `computer-use`

> Open the running app and click through the full scenario flow, then tell me where it
> breaks or feels wrong.

### `morning`

Two uses — one literal, one as product reference.

> Set up my morning brief to include the digital-twin build status.

> Read the morning brief skill as a design reference: it's the closest existing example
> of the daily-glance format I want for the Financial Command Centre. Extract the
> principles — what earns a place on a 30-second page, how it stays calm rather than
> alarming — and write them into `specs/dashboard.md`.

---

## Product-behaviour references

Not tools for building, but the closest existing specifications of features this app
should eventually have. Read them for behaviour, not for code.

### `cancel-unsubscribe`

> Read this skill as a behavioural reference. Recurring-subscription detection and
> cancellation is a feature of the digital twin's risk detection. Extract how it audits a
> statement for recurring charges and what confirmation it requires before a destructive
> action, and write that into `specs/recommendations.md` as the subscription-audit
> requirement.

### `file-expenses`

> Read this as a reference for receipt capture and duplicate detection, and fold the
> relevant behaviour into `specs/transactions.md`.

---

## Skipped

No honest use here, and forcing one would put noise in the repo: `grocery-shopping`,
`meal-delivery`, `prescription-refill`, `call-to-book`, `hire-help`, `return-refund`,
`event-planning`, `benepass-reimbursement`, `file-form`, `import-memory`.

If you want them exercised anyway, the only defensible framing is as UX references for
concierge-style flows — the digital twin's AI CFO has the same shape of problem: gather
context, confirm before acting, never surprise the user.
