# Financial command centre

## Objective

One view that orients the user in thirty seconds: where they stand, what is coming, and
whether anything needs attention.

The design principle is borrowed from a well-built morning brief — anything that does not
change a decision does not earn a place on the page. The failure mode for a financial
dashboard is not being too sparse; it is being a wall of charts nobody reads twice.

## Inputs

A single `GET /position` call returning stored results. No computation happens during the
request, per ADR-003.

## Processing

None at request time. The page renders what the position snapshot, latest health
assessment, active risk flags, and current forecast already contain.

If a required stored result is missing — a new user with no forecast yet — the page renders
its empty state for that section rather than triggering generation inline.

## Output

Five regions, in priority order:

**1. Position.** Net worth, liquid savings, total debt. The anchor figures.

**2. This month's cash flow.** Income, essential spending, discretionary spending,
remaining, each against the month before. Rendered as a flow, not a pie chart — the user
wants to know what is left, not the proportional breakdown of what is gone.

The month shown is the most recent one **with transactions**, named on the card, not the
current calendar month. On the 3rd of a month the current month holds three days, and for
a user whose last statement was a while ago it holds nothing — four zeros under a heading
is not a reading, it is the absence of one. Where there are no transactions at all the
region says so instead of showing zeros.

Every monthly figure in this product is derived from transactions, and the dashboard states
what it measured: which month, how many months of history exist, and how many transactions
stand behind them. A figure from one imported statement and a figure from eighteen months
of them are different claims.

**3. What is coming.** Obligations due in the next 30 days with dates and amounts, and
whether projected available funds cover them. This is the section that most often changes
a decision.

**4. Financial health.** Score with trajectory arrow, and the single largest contributing
factor. The full breakdown is one click away, not on the page.

**5. Attention.** Active risk flags, if any. When there are none, the region is absent
rather than showing a green all-clear, which trains the user to skim past it.

Every projected figure carries its generation date. A projection generated eight days ago
says so.

## Constraints

- The request performs no financial calculation and issues no forecast run.
- Server time under 500ms.
- Projected and actual figures are visually distinguishable, not merely labelled.
- Financial status is never encoded in colour alone — see `specs/../docs/` accessibility
  requirements and the accessibility review.
- The page does not display a figure the API did not supply.

## Acceptance criteria

- [ ] Renders from a single API call.
- [ ] Server time under 500ms with 18 months of transaction history.
- [ ] Every projected value shows its generation date.
- [ ] Stale projections are labelled as stale, with a manual refresh available.
- [ ] Empty states exist for every region, for a user with no data.
- [ ] The attention region is absent when there are no flags.
- [ ] No calculation occurs in frontend code.
- [ ] Readable and operable by keyboard and screen reader.
