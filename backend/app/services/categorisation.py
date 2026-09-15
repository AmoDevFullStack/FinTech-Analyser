"""Transaction categorisation. See specs/transactions.md step 5.

"Rules first, then similarity against the user's own corrected history, then a default
category with low confidence. Confidence is stored."

The order matters and so does the last clause. A correction the user made is the strongest
signal this system has about their own money — stronger than any rule shipped with the
product — but it is still applied only after an explicit rule match, because a rule is a
statement about what a description means and a correction is a statement about what one
merchant meant.

A user's correction is never overwritten by a later automatic pass: that is enforced by
`category_set_by_user` on the transaction, checked by every caller that would recategorise.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID

from app.core.db import DbSession
from app.models.category import Category, CategoryKind
from app.models.transaction import Transaction
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository

# Above this, two descriptions are the same merchant with different noise around it
# ("woolworths claremont" vs "woolworths sea point"). Below it, they are different
# merchants that happen to share a word, and inheriting a category would be a guess.
SIMILARITY_THRESHOLD = 0.82

CONFIDENCE_RULE = Decimal("0.900000")
CONFIDENCE_EXACT_CORRECTION = Decimal("0.990000")
CONFIDENCE_DEFAULT = Decimal("0.200000")

HISTORY_LIMIT = 5_000


@dataclass(frozen=True, slots=True)
class CategorySuggestion:
    category: Category | None
    confidence: Decimal
    basis: str  # "rule" | "correction_exact" | "correction_similar" | "default" | "none"


class CategorisationService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._categories = CategoryRepository(session)
        self._transactions = TransactionRepository(session)

    def corrected_history(self, *, user_id: UUID) -> dict[str, UUID]:
        """Normalised description to category, from transactions the user corrected.

        Later corrections win: a user who recategorises the same merchant twice meant the
        second one.
        """
        corrections: dict[str, UUID] = {}
        rows = sorted(
            (
                t
                for t in self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT)
                if t.category_set_by_user and t.category_id is not None
            ),
            key=lambda t: t.occurred_on,
        )
        for txn in rows:
            assert txn.category_id is not None
            corrections[txn.normalised_description] = txn.category_id
        return corrections

    def suggest(
        self,
        *,
        normalised_description: str,
        categories: list[Category],
        corrections: dict[str, UUID],
    ) -> CategorySuggestion:
        """Choose a category for one description, with the confidence and why.

        Pure given its arguments — the caller loads `categories` and `corrections` once
        per import rather than once per row, which is what keeps a 10,000-row file inside
        the spec's performance criterion.
        """
        by_id = {c.id: c for c in categories}

        rule_match = next(
            (c for c in categories if c.name.lower() in normalised_description), None
        )
        if rule_match is not None:
            return CategorySuggestion(rule_match, CONFIDENCE_RULE, "rule")

        exact = corrections.get(normalised_description)
        if exact is not None and exact in by_id:
            return CategorySuggestion(
                by_id[exact], CONFIDENCE_EXACT_CORRECTION, "correction_exact"
            )

        best_id: UUID | None = None
        best_score = Decimal("0")
        for description, category_id in corrections.items():
            score = SequenceMatcher(None, description, normalised_description).ratio()
            if score > float(best_score):
                best_score = Decimal(str(round(score, 6)))
                best_id = category_id
        if best_id is not None and best_score >= Decimal(str(SIMILARITY_THRESHOLD)):
            if best_id in by_id:
                # Confidence IS the similarity: a 0.83 match is a weaker claim than a
                # 0.97 one, and storing both as the same number would throw away the only
                # information a reviewer has about which suggestions to check.
                return CategorySuggestion(by_id[best_id], best_score, "correction_similar")

        fallback = next(
            (c for c in categories if c.kind is CategoryKind.DISCRETIONARY), None
        )
        if fallback is None:
            return CategorySuggestion(None, Decimal("0"), "none")
        return CategorySuggestion(fallback, CONFIDENCE_DEFAULT, "default")

    def recategorise_uncorrected(self, *, user_id: UUID) -> int:
        """Re-run categorisation over rows the user has not corrected.

        Called after a correction, so one correction improves every similar transaction
        already imported. Rows with `category_set_by_user` are skipped: "A user correction
        ... is never overwritten by a later automatic pass."
        """
        categories = self._categories.list_for_user(user_id=user_id)
        corrections = self.corrected_history(user_id=user_id)
        updated = 0

        for txn in self._transactions.for_user(user_id=user_id, limit=HISTORY_LIMIT):
            if txn.category_set_by_user:
                continue
            suggestion = self.suggest(
                normalised_description=txn.normalised_description,
                categories=categories,
                corrections=corrections,
            )
            if suggestion.category is None:
                continue
            if txn.category_id != suggestion.category.id:
                txn.category_id = suggestion.category.id
                txn.category_confidence = suggestion.confidence
                updated += 1

        self._session.commit()
        return updated

    def correct(
        self, transaction: Transaction, *, category_id: UUID, propagate: bool = True
    ) -> int:
        """Record a user's correction and, by default, learn from it immediately.

        Returns the number of other transactions the correction moved.
        """
        transaction.category_id = category_id
        transaction.category_set_by_user = True
        transaction.category_confidence = Decimal("1.000000")
        self._session.commit()

        if not propagate:
            return 0
        return self.recategorise_uncorrected(user_id=transaction.user_id)
