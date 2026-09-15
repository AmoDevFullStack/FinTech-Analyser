# Scenario simulator

## Objective

Let a user model a financial decision before committing to it, and see its full downstream
effect against the do-nothing baseline.

This is the product. Everything else exists to make this feature's numbers trustworthy.

## Worked example

A user is considering a R350,000 vehicle: R50,000 deposit, 11.75% over 72 months, plus
insurance, fuel, and maintenance. They want to know what it costs them, not monthly, but in
total — in cash flow, in emergency cover, in when they become debt free, and in what they
are worth in five years.

## Inputs

Scenario types for v1: vehicle purchase, property purchase or move, income change, new
loan, changed debt repayment, changed monthly savings, discretionary expense.

Assumptions vary by type. Vehicle purchase takes purchase price, deposit, annual rate, term
in months, insurance monthly, fuel monthly, maintenance monthly, and an optional trade-in
value.

Every scenario also references a position snapshot captured at creation.

## Processing

1. On creation, capture a `PositionSnapshot` of the user's current computed position and
   store its identifier on the scenario. The scenario is forever evaluated against this
   snapshot unless re-baselined.

2. On run, load the snapshot and the assumptions. Nothing is read from live financial
   tables during a run.

3. Compute the baseline projection — the user's trajectory with no change — over the
   horizon.

4. Compute the scenario projection: apply the assumption deltas to the position, run
   amortisation for any new debt, apply recurring cost changes to cash flow, and project
   forward month by month.

5. Derive the impact summary by differencing the two projections.

6. Persist a `ScenarioResult` carrying the projection, the baseline, the assumptions hash,
   and the engine version.

All arithmetic is in `app/domain/`. The scenario service orchestrates; it does not
calculate.

## Output

Impact summary: monthly cash-flow delta, disposable income after, debt-to-income before and
after, emergency fund months after, net worth at horizon, and projected debt-free date.

Period series for scenario and baseline together, so before-and-after renders from one
response.

The assumptions, visible and editable. A projection whose assumptions are hidden cannot be
argued with, and one that cannot be argued with will not be believed.

## Constraints

- A run writes nothing to accounts, transactions, debts, income, or goals. Structural, per
  ADR-005.
- Identical assumptions against an identical snapshot produce identical output, always.
- The snapshot date is displayed wherever scenario results are shown.
- Applying a scenario to real state is a separate endpoint requiring explicit confirmation,
  and produces an audit record.
- A scenario referencing a snapshot older than 30 days is flagged for re-baselining.

## Acceptance criteria

- [ ] User can create, edit, run, save, re-run, and delete a scenario.
- [ ] Running produces impact summary and both period series.
- [ ] A run issues zero writes to real financial tables, asserted by test.
- [ ] Re-running with identical inputs produces byte-identical figures.
- [ ] Baseline comparison is returned in the same response.
- [ ] Two scenarios can be compared against each other and the baseline.
- [ ] Re-baselining captures a fresh snapshot and re-runs.
- [ ] Applying writes real records, requires confirmation, and logs an audit entry.
- [ ] Snapshot age is displayed; over 30 days is flagged.
- [ ] Runs completing within 3 seconds return synchronously; longer runs queue.
- [ ] Domain tests assert amortisation against independently derived reference figures.
