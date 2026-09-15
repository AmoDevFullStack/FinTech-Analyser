# Risk detection

## Objective

Tell the user about a problem before it happens, with enough specificity to act on, and
without crying wolf.

## Inputs

Current forecast periods, upcoming obligations, position, health assessment components,
and trailing spending baselines by category.

## Detected risks

**Projected cash-flow shortfall.** A forecast period where projected outflows exceed
projected inflows plus available liquid funds. Reports the month and the amount short.

**Obligation coverage gap.** A specific upcoming debit order or instalment that projected
available funds do not cover on its due date. The most actionable flag the system produces,
because it names a date and an amount.

**Emergency reserve depletion.** Projected emergency cover falling below one month within
the horizon.

**Debt burden threshold.** Debt obligations exceeding 40% of net income currently or in
projection.

**Anomalous spending.** A category exceeding the user's own trailing baseline by a
materially significant margin, measured against their income rather than an absolute
amount. R2,000 over on groceries means something different at R20,000 income than at
R80,000.

**Credit utilisation.** Revolving utilisation above 70%.

## Processing

Evaluated by a worker after each forecast regeneration and after each import.

Every flag records the engine result that produced it. A flag whose figure cannot be traced
back to a computation is not created — the system must be able to explain itself when the
user asks why.

**Deduplication.** An active flag of the same type is updated rather than duplicated.

**Suppression.** A dismissed flag does not reappear for 30 days unless its severity
increases. A flag that reappears daily after dismissal trains the user to ignore the whole
feature.

**Materiality.** Below a threshold scaled to income, no flag is raised.

## Output

Per flag: type, severity, the projected date it materialises, the quantified amount, a
plain-language explanation, and the computation reference.

## Copy conventions

Direct, specific, never alarmist, never shaming.

- Good: "Your vehicle instalment of R6,843 is due on 25 October. Projected available funds
  that week are R4,210."
- Bad: "Warning! You are heading for financial trouble."
- Bad: "You have been overspending on dining out."

State the figure and the date. Do not characterise the person. The user knows they went out
to eat; what they do not know is that the debit order will bounce.

## Constraints

- Every flag traces to a computed result.
- Flags state a date and an amount.
- Dismissed flags stay dismissed for 30 days unless severity increases.
- No flag is raised below the materiality threshold.
- Copy never uses moral language about spending.

## Acceptance criteria

- [ ] All six risk types detect against seeded scenarios.
- [ ] Every flag carries a computation reference.
- [ ] Flags include projected date and quantified amount.
- [ ] Re-evaluation updates rather than duplicates active flags.
- [ ] Dismissal suppresses for 30 days; escalating severity overrides suppression.
- [ ] Materiality threshold scales with income.
- [ ] Copy review confirms no shaming or alarmist language.
