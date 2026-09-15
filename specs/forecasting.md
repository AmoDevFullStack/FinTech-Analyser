# Forecasting

## Objective

Project the user's financial trajectory forward from how they actually behave, not from
what they say they intend, and be honest about the uncertainty in doing so.

## Inputs

Historical transactions, declared and inferred recurring income and expenses, debt
schedules, goal contributions, and explicit user assumptions: salary growth, inflation,
horizon.

Minimum viable history is three months. Below that, projections are generated from declared
values only and labelled low-confidence.

## Processing

Runs asynchronously in a worker, per ADR-003.

**1. Derive behavioural parameters.** From history: median monthly income, essential
spending baseline, discretionary spending baseline and variability, savings rate, and
seasonal effects where twelve months of history exist.

Use medians rather than means. One bonus month or one medical emergency should not shift
the baseline, and means are exactly the statistic that lets them.

**2. Apply assumptions.** Salary growth annually on the anniversary of the last increase.
Inflation to essential spending. Discretionary spending held flat in real terms unless the
user says otherwise.

Defaults are visible and editable. Inflation defaults to 5.0% and salary growth to 5.0%,
both stated in the UI as assumptions rather than facts.

**3. Project month by month** to the horizon, to 60 months: income, essential spending,
discretionary spending, cash flow, savings balance, per-debt balance via amortisation,
emergency fund coverage in months, and net worth.

Debt service is part of projected outflows. Until engine 1.1.0 it was not: projections
subtracted only essential and discretionary spending, which overstated cash flow and
savings by the whole monthly debt repayment for every month of the horizon. From 1.1.0
the user's debt set is amortised across the horizon, so the instalment leaves cash flow,
the principal component builds net worth, and the balance runs down to zero. Figures
produced before 1.1.0 are not comparable with figures produced after it; stored forecasts
are regenerated rather than migrated.

**4. Persist** the full period series with `generated_at`, `input_snapshot_id`, the
assumptions, and the engine version.

**5. Invalidate** on material change: transaction import, income change, new or closed
debt, goal change, or assumption edit. Marking stale is enough — regeneration is queued,
not immediate.

## Accuracy measurement

Each month, compare the projection made for that month against realised actuals. Store
absolute and percentage error per metric.

Reported to the user as a plain accuracy statement, and used to adjust the discretionary
spending baseline where error is persistently one-directional.

A forecasting product that never checks itself is a horoscope.

## Output

Period series per metric. Generation date and staleness. Accuracy history. The assumptions
used, always.

## Constraints

- Never computed during a request.
- Always reproducible from the persisted snapshot and assumptions.
- All arithmetic in `Decimal`; statistical fitting may use float in the analytics layer, but
  the conversion boundary is explicit and documented.
- Projections are labelled projections. The word "will" does not appear in copy describing
  them.
- Below three months of history, output is labelled low-confidence.

## Acceptance criteria

- [ ] Generates 60-month projections across all five metrics.
- [ ] Runs in a worker; the API only reads stored results.
- [ ] Stored with assumptions, snapshot reference, and engine version.
- [ ] Reproducible: regenerating from the same stored inputs yields identical figures.
- [ ] Material changes mark the forecast stale.
- [ ] Stale forecasts are visibly stale, with manual refresh.
- [ ] Assumptions are visible and editable, and editing triggers regeneration.
- [ ] Accuracy is measured monthly and exposed.
- [ ] Fewer than three months of history yields a labelled low-confidence forecast.
- [ ] Baseline statistics use medians, asserted by test against a history containing outliers.
