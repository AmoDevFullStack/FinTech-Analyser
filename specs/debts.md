# Debt intelligence

## Objective

Show the user what their debt actually costs, how long it actually lasts, and what changes
if they pay differently.

Most people know their instalment. Few know their total interest, and fewer know that
R500 extra a month on the right debt can shorten their timeline by years.

## Inputs

Per debt: type, original principal, current balance, annual nominal rate, minimum payment,
contractual instalment where fixed, term, start date.

For strategy comparison: total monthly amount available for debt repayment.

## Processing

**Amortisation.** Monthly instalment from the standard annuity formula. Per period:
interest on opening balance, principal as the remainder, closing balance reduced
accordingly. Interest rounds per period, matching what a lender does — rounding only at the
end produces a schedule that matches no real statement.

The final instalment is adjusted so the closing balance is exactly zero.

Extra payments apply wholly to principal and shorten the term rather than reducing the
instalment.

**Strategy comparison** across the user's full debt set, with the same total monthly amount:

- *Avalanche* — surplus to the highest rate first. Mathematically optimal.
- *Snowball* — surplus to the smallest balance first. Slower, but produces early wins that
  measurably improve adherence.
- *Consolidation* — single facility at a blended rate, where the user supplies a rate and
  any initiation fee.

For each: total interest paid, months to debt free, and the monthly schedule.

The comparison states the cost difference between avalanche and snowball in rand and in
months, and names the conditions under which the ranking changes. Where the difference is
small, the system says so, because a strategy the user abandons is worse than a slightly
suboptimal one they finish.

**What-if.** The marginal effect of an additional R100, R500, or R1,000 per month: months
saved and interest saved.

## Output

Per debt: full schedule, total interest, payoff date, and the effect of extra payment.

Across debts: strategy comparison with total cost, time to free, and the crossover
conditions.

## Constraints

- All arithmetic in `app/domain/`, `Decimal` throughout, per the
  `financial-domain-engine` skill.
- Schedules are deterministic and reproducible.
- Every engine is tested against reference figures derived independently — a spreadsheet
  model or a published lender schedule, never the code's own output.
- Assumptions stated: fixed rate, monthly compounding, payment at period end, no fees
  unless supplied.
- The system does not recommend a strategy as advice. It presents costs and lets the user
  choose.

## Acceptance criteria

- [ ] Amortisation matches an independently derived reference schedule to the cent.
- [ ] Principal components sum to the original principal.
- [ ] Closing balance never goes negative; the final balance is exactly zero.
- [ ] Opening balance of period n equals closing balance of period n−1.
- [ ] Extra payments shorten the term and reduce total interest, asserted as an invariant.
- [ ] All three strategies compute across the user's real debt set.
- [ ] The comparison quantifies the avalanche-versus-snowball difference in rand and months.
- [ ] What-if returns months and interest saved for each increment.
- [ ] Property-based tests cover plausible principal, rate, and term ranges.
