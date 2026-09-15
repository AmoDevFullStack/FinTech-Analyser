# Feature specifications

Each file here is the behavioural contract for one capability. Specs describe *what* a
feature does and how it must behave. They do not describe code structure — that is
`docs/architecture.md` — and they do not revisit decisions — that is `docs/decisions.md`.

Read the relevant spec before implementing. If implementation reveals the spec is wrong,
change the spec in the same pull request rather than letting the two disagree.

## Shape of a spec

Every file follows the same sections, so an agent knows where to look:

- **Objective** — what problem this solves for the user
- **Inputs** — what the feature receives
- **Processing** — the ordered behaviour, including which engines are involved
- **Output** — what the user or caller receives
- **Constraints** — what must never happen
- **Acceptance criteria** — checkboxes that make the spec testable

## Index

| Spec | Covers |
|---|---|
| `accounts.md` | Account creation, balance derivation, archival |
| `transactions.md` | Import, deduplication, categorisation, recurrence |
| `dashboard.md` | The financial command centre |
| `scenarios.md` | Hypothetical decision simulation |
| `forecasting.md` | Projection generation and accuracy measurement |
| `debts.md` | Amortisation, repayment strategy comparison |
| `goals.md` | Goal tracking against actual cash flow |
| `financial-health.md` | Resilience scoring |
| `risk-detection.md` | Forward-looking risk flags |
| `ai-cfo.md` | Natural-language interaction |
| `recommendations.md` | Rules-based suggestions |
| `credit.md` | Credit profile, deferred to v2 |
