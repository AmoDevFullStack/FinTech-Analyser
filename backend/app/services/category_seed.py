"""The system chart of accounts. See specs/transactions.md step 5 and specs/dashboard.md.

Before this existed, a new user had no categories at all, so every imported transaction
fell through categorisation with `basis="none"`, every cash-flow figure read zero, and the
health score had nothing to score. The demo seeder created three categories by hand
(Salary, Groceries, Dining out) and the dashboard mock was built against those three,
which is why the gap was not obvious.

These are system categories: `user_id IS NULL`, visible to everyone, owned by nobody.
`CategoryRepository.list_for_user` already returns them alongside a user's own.

The list is exactly the canonical name of every purpose the detection engine can return
(`PURPOSE_CATEGORY_NAME`), with that purpose's kind. Keeping the two in lockstep is the
whole point: a purpose the engine can detect but the chart of accounts has no home for
would be detected and then discarded. The test that asserts this correspondence is the one
that stops the two drifting.

Rent has a category here for the same reason it has a rule in the taxonomy. It is the
largest monthly commitment for a large share of users, it is essential rather than
discretionary, and a system that cannot name it produces a cash-flow picture that is wrong
by the size of someone's rent.
"""

from __future__ import annotations

from app.core.db import DbSession
from app.domain.payment_taxonomy import PURPOSE_CATEGORY_NAME, PURPOSE_KIND, SpendingPurpose
from app.models.category import Category, CategoryKind
from app.repositories.category import CategoryRepository


def system_category_definitions() -> list[tuple[str, CategoryKind]]:
    """Every system category, as (name, kind), in a stable order.

    Derived from the purpose taxonomy rather than written out again, so a purpose added to
    `app/domain/payment_taxonomy.py` cannot be left without somewhere to file it.
    """
    return [
        (PURPOSE_CATEGORY_NAME[purpose], CategoryKind(PURPOSE_KIND[purpose].value))
        for purpose in SpendingPurpose
        if purpose is not SpendingPurpose.UNKNOWN
    ]


def ensure_system_categories(session: DbSession) -> list[Category]:
    """Create any missing system category and return the full set.

    Idempotent, and safe to call on every registration: existing rows are matched by name
    and left alone, including their kind. A user who has been shown "Fuel" as essential
    spending for six months should not have it silently become discretionary because this
    file changed — moving an existing category between kinds moves every historical figure
    derived from it, and that is a migration with a reason recorded, not a seeding
    side effect.
    """
    repository = CategoryRepository(session)
    existing = {
        category.name.lower(): category
        for category in repository.list_system()
    }

    created: list[Category] = []
    for name, kind in system_category_definitions():
        if name.lower() in existing:
            continue
        category = Category(user_id=None, name=name, kind=kind)
        session.add(category)
        created.append(category)

    if created:
        session.flush()

    return [*existing.values(), *created]
