# Domain engine conventions

Rules for code in `backend/app/domain/`, the deterministic engines that produce every figure
the product shows. ADR-001 (money is `Decimal`) and ADR-002 (the language model never
computes) are the decisions behind them; this file is how those decisions show up in code.
Code comments cite these rules by number.

---

## Rule 1 — Engines are pure

An engine takes values and returns values. It does not touch the database, the network, the
clock, or configuration, and it knows nothing about accounts, transactions, or users. Every
date it needs, `as_of` above all, is an explicit argument, never `date.today()`. A test can
then pin any date, and the same inputs always produce the same output.

Gathering inputs belongs to services (`app/services/`). Services assemble an engine's
inputs and shape its outputs; they compute nothing themselves.

## Rule 2 — Money is `Decimal`, end to end

No `float` anywhere in `app/domain/`: CI fails the build on `float(`. Amounts cross the API
as strings, never JSON numbers (ADR-001, `app/core/money.py`).

## Rule 3 — Rounding is stated, not incidental

Every engine documents its rounding in its docstring. The default is to quantise
period-level money results to two places with `ROUND_HALF_UP`, and to carry full precision
in between. Where a schedule must close exactly (an amortised loan), the final period
absorbs the rounding residue, so the closing balance is exactly zero, as on a lender's
statement.

## Rule 4 — Expected values come from outside the code

A test's expected figure is derived independently: by hand, in a spreadsheet, from the
standard formula, or from what a real statement line says. It is never copied from what
the code currently returns. If a document's worked example disagrees with an independent
calculation, the test asserts the independent value and the document is flagged for
correction.

## Rule 5 — Invariants are tested as well as examples

Alongside reference figures, every engine has tests for the properties that must always
hold. For example: a projection with no change in its inputs is flat, a fully paid schedule
ends at zero, and scenario results never depend on real stored state.

## Rule 6 — A changed result is a behavioural change

Stored results carry `assumptions_hash` and `engine_version` so they can be reproduced. If
a change to an engine would make the same inputs produce a different stored result,
increment `engine_version` and say so in the pull request: users may have saved the old
figure.
