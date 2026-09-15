# Goals

## Objective

Connect what the user says they want to what their money actually does, and be honest when
the two do not meet.

## Inputs

Target amount, target date, priority, optional linked savings account, optional planned
monthly contribution.

## Processing

**Progress** is evidenced, not asserted. Where a goal is linked to an account, progress is
the account's balance movement attributable to the goal. Where it is not, progress is the
sum of recorded contributions. A goal with neither shows no progress rather than an
optimistic estimate.

**Required contribution** is target minus current, divided by months remaining, adjusted
for interest where the linked account bears it.

**Projected achievement date** uses the actual observed contribution rate over the last
three months, not the planned rate. The gap between the two is the most useful thing this
feature produces.

**Achievability.** Where the required contribution exceeds projected available cash flow,
the goal is not achievable at current behaviour. The system states this plainly and
quantifies the shortfall — monthly amount short, and how far the date slips at the current
rate.

Indefinite progress bars on unachievable goals are a way of avoiding telling the user
something true.

**Competition.** Where the sum of required contributions across active goals exceeds
projected available cash flow, the system shows which goals are funded in priority order
and how far the remainder slip. Goals are not modelled in isolation because they are not
funded in isolation.

## Output

Per goal: current amount, target, required monthly contribution, observed contribution
rate, projected achievement date, achievability with quantified gap.

Across goals: total required, available cash flow, and the funding order with slippage.

## Constraints

- Progress is derived from actual movements, never from the planned contribution.
- Projections use observed behaviour, not intent.
- An unachievable goal is stated as unachievable with the gap quantified.
- Goal projections use the same forecasting engine as everything else; there is no separate
  goal maths.

## Acceptance criteria

- [ ] User can create, edit, prioritise, and delete goals.
- [ ] Progress derives from linked account movement or recorded contributions.
- [ ] Required monthly contribution is computed, including interest where applicable.
- [ ] Projected achievement date uses the observed three-month rate.
- [ ] Unachievable goals are labelled with the monthly shortfall and date slippage.
- [ ] Competing goals show funding order and slippage against available cash flow.
- [ ] A goal with no linked account and no contributions shows zero progress, not an estimate.
