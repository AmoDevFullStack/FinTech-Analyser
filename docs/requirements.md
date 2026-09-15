# Requirements

What the system must do. Structure is defined in `docs/architecture.md`; decisions in
`docs/decisions.md`; per-feature detail in `specs/`. This file is the top of that chain —
if a requirement here has no corresponding spec, the spec is missing.

Requirements use "shall" for mandatory behaviour and "may" for optional behaviour.
Currency is South African rand throughout; multi-currency is explicitly out of scope for
v1.

---

## 1. Financial profile

The system shall maintain a continuously updated financial profile per user, comprising
income, employment, recurring expenses, assets, liabilities, credit accounts, savings,
and financial goals.

The profile shall be derived from recorded data wherever possible rather than asked for.
A user who has imported six months of transactions should not be asked what they spend on
groceries.

Where the system infers a profile value, it shall record that the value is inferred, show
the user what it inferred, and allow correction. An inferred value the user has corrected
shall not be silently re-inferred.

The profile shall expose a point-in-time position — balances, obligations, net worth — that
can be snapshotted and referenced by a scenario.

## 2. Accounts

Users shall be able to create accounts of type: transactional, savings, credit card, loan,
home loan, vehicle finance, investment, and manual asset.

Each account shall carry a current balance, a currency, an institution, and an opening
date. Interest-bearing accounts shall carry a rate. Credit accounts shall carry a limit.

Balances shall be derived from transactions where transactions exist, and entered manually
where they do not. The system shall not present a derived balance and a manual balance as
if they were equally reliable.

Users shall be able to archive an account without deleting its history, because closed
accounts remain part of the financial record.

## 3. Transactions

Users shall be able to import transactions by CSV upload, with support for the export
formats of the major South African banks.

The system shall detect and prevent duplicate imports — the same transaction arriving
twice from different sources shall be recognised as one transaction. Matching methodology
follows reconciliation practice: date window, amount, and description similarity, with
unmatched candidates surfaced to the user rather than auto-resolved. See
`specs/transactions.md`.

Transactions shall be automatically categorised, with a confidence indication. Users shall
be able to correct a category, and a correction shall improve future categorisation of
similar transactions for that user.

Users shall be able to search, filter by date range, account, category, and amount range,
and view a running history.

The system shall identify recurring transactions — salary, debit orders, subscriptions —
and distinguish them from one-off spending, because recurring commitments and discretionary
spending behave differently in a projection.

Transfers between a user's own accounts shall be recognised as transfers, not as income
and expenditure, so they do not distort cash-flow figures.

## 4. Financial command centre

The system shall provide a consolidated view showing current position, cash flow for the
current period, upcoming obligations, financial health, and any active risk flags.

The view shall be readable in roughly thirty seconds. Anything that does not change a
decision does not belong on it.

Every projected figure displayed shall be labelled as projected and carry the date it was
generated. See ADR-003 on the staleness contract.

The view shall load from stored results and shall not trigger computation.

## 5. Scenario simulation

Users shall be able to create hypothetical scenarios modelling a financial decision.
Supported scenario types for v1: vehicle purchase, property purchase or move, income
change, new loan, changed debt repayment, changed monthly savings, and a discretionary
expense such as a holiday.

A scenario shall never modify the user's actual financial state. Isolation is structural,
per ADR-005.

A scenario shall capture its assumptions explicitly and reference a snapshot of the user's
position at creation time. The snapshot date shall be visible, and users shall be able to
re-baseline a scenario against their current position.

Running a scenario shall produce: monthly cash-flow impact, disposable income impact,
debt-to-income ratio, savings trajectory, emergency fund trajectory, projected net worth,
and debt repayment timeline.

Scenarios shall be saved, re-run with altered assumptions, and compared against each other
and against the do-nothing baseline.

Users shall be able to apply a scenario to their real financial state as an explicit,
confirmed, audited action.

## 6. Forecasting

The system shall generate projections of cash flow, savings, debt balances, emergency
fund, and net worth for horizons up to 60 months.

Projections shall be derived from historical behaviour plus explicit assumptions, and the
assumptions shall be visible and editable by the user. A projection whose assumptions are
hidden cannot be argued with, and one that cannot be argued with will not be trusted.

Every stored projection shall retain the assumptions and input snapshot that produced it,
so it is reproducible.

Projections shall be regenerated on a schedule, on material change, and on demand. They
shall be read from storage, never computed during a request. See ADR-003.

The system shall record forecast accuracy by comparing prior projections against realised
actuals, and shall use that comparison to improve subsequent projections.

## 7. Financial time machine

The system shall analyse historical financial data to identify trends in spending,
lifestyle inflation, changes in recurring commitments, debt growth or reduction, and
changes in saving behaviour.

Analysis shall decompose period-over-period change into drivers — income change,
category-level spending change, one-off events, and timing effects — rather than reporting
an undifferentiated total. Methodology follows variance analysis practice.

The system shall apply a materiality threshold appropriate to the user's income and shall
not surface immaterial variances.

## 8. Debt intelligence

The system shall model each debt's repayment timeline, total interest cost, and the effect
of additional payments.

The system shall compare repayment strategies — avalanche, snowball, and consolidation —
on the user's actual debt set, showing the total cost and time-to-free of each, and shall
identify the conditions under which the ranking changes.

Amortisation shall match what a lender would produce: per-period interest rounding, final
period adjustment to a zero closing balance.

## 9. Goals

Users shall be able to define financial goals with a target amount and a target date.

The system shall connect each goal to actual cash flow and determine whether current
behaviour achieves it, shall project the achievement date at current behaviour, and shall
state the monthly contribution required to meet the target date.

Where a goal is unachievable at current behaviour, the system shall say so plainly and
quantify the gap rather than displaying indefinite progress.

Goals shall compete honestly: the system shall show when funding one goal delays another.

## 10. Financial health

The system shall compute a financial health assessment from cash-flow stability, debt
exposure, savings rate, emergency reserve coverage, spending behaviour, and fixed
commitment ratio.

The assessment shall be explainable: every component contribution shall be inspectable,
and the score shall be reproducible from stored inputs. A score a user cannot interrogate
is a number they will ignore.

The system shall show the score's trajectory over time, not only its current value.

## 11. Risk detection

The system shall identify and surface: projected cash-flow shortfall, debt exposure beyond
a defined threshold, insufficient emergency reserve, anomalous spending relative to the
user's own baseline, and upcoming obligations exceeding projected available funds.

Risks shall be surfaced before they materialise, with the projected date and the
quantified shortfall.

Alerts shall be actionable and shall not shame. Copy conventions in `specs/risk-detection.md`.

The system shall not generate an alert it cannot explain in terms of computed figures.

## 12. AI CFO

Users shall be able to ask financial questions in natural language and receive answers
grounded in their own computed financial data.

Every figure in an answer shall originate from a domain engine. The language model shall
not compute, estimate, or infer a financial figure. See ADR-002.

Where a question cannot be answered by an available engine, the system shall say so
rather than approximating.

The system shall remain usable with the language model unavailable: figures render without
narration.

Answers shall cite what they are based on — which accounts, which period, which
assumptions.

## 13. Security and privacy

Every financial record shall be scoped to its owning user, enforced at the data access
layer.

Credentials and secrets shall never reach the frontend.

Financial data sent to a third-party model provider shall be the minimum required for the
request, derived from result objects rather than raw records.

Users shall be able to export their complete data and to delete their account and its
data.

Authentication shall support session expiry and password reset. Multi-factor authentication
is desirable for v1 and required before any real bank connection.

## 14. Non-functional

| Requirement | Target |
|---|---|
| Dashboard load | Under 500ms server time, reading stored results |
| Scenario run | Under 3 seconds synchronous, queued beyond that |
| Forecast generation | Asynchronous, no user-facing latency |
| Transaction import | 10,000 rows without timeout |
| Financial calculation | Deterministic and reproducible, always |
| Availability | Single-region is acceptable for v1 |

Determinism is the one entry above that is not a target but a constraint. A performance
miss is a defect; a non-reproducible figure is a failure of the product thesis.

## 15. Out of scope for v1

Live bank connections via aggregator, credit bureau integration, multi-currency,
multi-user households, tax computation, investment portfolio tracking with live prices,
and mobile applications. Each is anticipated by the architecture but none is built.

Nothing in this document constitutes financial advice, and the product shall not present
its output as such.
