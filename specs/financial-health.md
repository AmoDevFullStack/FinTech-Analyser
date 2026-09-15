# Financial health

## Objective

A single number expressing financial resilience — how well the user would withstand a
setback — that the user can interrogate component by component.

A score nobody can interrogate is a number they will ignore, or worse, trust blindly.

## Inputs

From the current position: monthly income, essential spending, discretionary spending,
total debt, monthly debt obligations, liquid savings, credit utilisation, and cash-flow
variability over the trailing six months.

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

Computed by a worker on schedule and on material change. Stored with the full component
breakdown.

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
- [ ] Changing weights does not retroactively alter stored assessments.
- [ ] Domain tests cover boundary cases at each band edge.
