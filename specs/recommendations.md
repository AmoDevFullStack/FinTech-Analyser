# Recommendations

## Objective

Surface specific, quantified actions the user could take, derived from their own figures.

Recommendations are produced by rules over computed results. The model phrases them; it
does not originate them. A suggestion the system cannot justify with a number is not a
suggestion, it is an opinion.

## Rules

Each rule states a trigger condition, the computation that quantifies it, and the action.

| Rule | Trigger | Quantifies |
|---|---|---|
| Redirect to highest-rate debt | Surplus exists and more than one debt | Interest and months saved |
| Build emergency cover | Cover below three months | Monthly amount to reach three months |
| Subscription audit | Recurring discretionary series above a threshold share of discretionary spend | Annual cost of the series |
| Utilisation reduction | Revolving utilisation above 70% | Amount to bring below 30% |
| Goal contribution shortfall | Required exceeds observed rate | Monthly gap and date slippage |
| Refinance candidate | A debt's rate materially above the user's weighted average | Interest saving at a stated alternative rate |
| Surplus not allocated | Persistent unallocated surplus over three months | Monthly amount and its effect if saved or repaid |

## Subscription audit

Detect recurring discretionary series from the recurrence groups produced by transaction
processing. For each, report monthly and annual cost and the date last charged.

Where the user chooses to cancel, the system provides the merchant's stated cancellation
route where known. It does not cancel on the user's behalf — a destructive external action
requires the user, and the confirmation discipline modelled by the cancellation concierge
flow applies: show the plan, get an explicit yes, never act silently.

## Processing

Evaluated by a worker after forecast regeneration. Each recommendation stores its rule
identifier, the computed figures, and the result reference that produced them.

Ranked by quantified benefit, capped at five active at a time. A list of twenty
recommendations is a list nobody acts on.

Dismissal suppresses for 60 days unless the quantified benefit materially increases.

## Constraints

- Every recommendation is produced by a rule, never by the model.
- Every recommendation carries a quantified benefit and its computation reference.
- Never framed as advice. "Redirecting R500 here saves R14,200 in interest" is a
  calculation; "you should redirect R500" is advice.
- No recommendation suggests a product, provider, or instrument.
- Maximum five active.

## Acceptance criteria

- [ ] All seven rules evaluate against seeded data.
- [ ] Each recommendation carries quantified benefit and computation reference.
- [ ] Ranking is by benefit; the list is capped at five.
- [ ] Dismissal suppresses for 60 days with an escalation override.
- [ ] Subscription audit identifies recurring discretionary series with annual cost.
- [ ] No recommendation text asserts what the user should do.
- [ ] The model's role is limited to phrasing, asserted by review of the prompt contract.
