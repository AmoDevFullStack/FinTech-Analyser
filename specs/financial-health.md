# Financial health

## Objective

A single number expressing financial resilience — how well the user would withstand a
setback — that the user can interrogate component by component.

A score nobody can interrogate is a number they will ignore, or worse, trust blindly.

## Inputs

**The score is per calendar month.** Each month is scored on its own transactions and its
own closing balance, stored against that month, and re-scored when later data changes it.

Before this, the score described "now", computed over the current calendar month. That
made it unreadable on the 3rd of a month and wrong for anyone whose last statement was a
while ago: with no transactions this month, income and essential spending were zero, so
emergency cover was zero months however much was in savings, and cash-flow margin, savings
rate and debt-to-income all divided by a zero income. A user who added an emergency fund
watched the score not move — correctly, and uselessly.

Per assessed month: income, essential spending, discretionary spending, saving and debt
payments from that month's transactions; liquid savings from that month's closing balance;
and cash-flow variability over the six months ending with it.

As they stand today, identically for every month: the debts' contractual minimum payments,
and credit-card balances and limits. Neither is recorded historically. Every assessment
stores which inputs were which, in `breakdown.historical_basis`, so a reader comparing
March with September knows which components could move and which could not.

## Processing

Six weighted components, each scored 0–100, combined into an overall score.

| Component | Weight | Measures |
|---|---|---|
| Emergency cover | 25% | Liquid savings ÷ monthly essential spending |
| Debt burden | 20% | Monthly debt obligations ÷ net income |
| Cash-flow margin | 20% | Surplus ÷ income |
| Savings rate | 15% | Amount saved ÷ income |
| Credit utilisation | 10% | Revolving balance ÷ limit |
| Cash-flow stability | 10% | Variability of surplus over six months |

Each component maps its ratio to a score through a documented band function, not a linear
scale. Three months of emergency cover is materially better than two; eight is not
materially better than seven.

Weights and bands live in one versioned module, and the version is stored with every
assessment. A score computed in March under different weights is not comparable to one
computed in September unless both versions are known.

Computed by a worker on schedule and on material change. A material change re-scores the
last 12 months, not only the current one: an imported statement usually carries months
whose scores were computed before those transactions existed. Stored with the full
component breakdown, one row per month, corrected in place on re-assessment.

## Output

Overall score, each component's ratio, band, score, and weighted contribution, the largest
positive and negative contributors, score history, and the weights version.

## Constraints

- Reproducible from the stored inputs and weights version.
- Never stored without its component breakdown.
- Not presented as a credit score and not described as one.
- No component is a black box; each has a stated formula and band table.
- Copy describes the score as an assessment of resilience, not a judgement of the person.

## Acceptance criteria

- [ ] All six components compute with documented band functions.
- [ ] The overall score is the weighted sum, reproducible from stored inputs.
- [ ] Every assessment stores its breakdown and weights version.
- [ ] The API returns the breakdown alongside the score.
- [ ] Largest positive and negative contributors are identified.
- [ ] History is retained and trajectory is derivable.
- [ ] Every assessment names the month it is about, and one month has one assessment.
- [ ] A month is scored on its own transactions and its own closing balance.
- [ ] Each assessment records which inputs are the month's own and which are current.
- [ ] Changing weights does not retroactively alter stored assessments.
- [ ] Domain tests cover boundary cases at each band edge.
