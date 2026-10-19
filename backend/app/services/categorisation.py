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

Precedence, in full:

    1. rule            — a category whose own name appears in the description
    2. correction_exact  — this exact description, corrected by this user before
    3. correction_similar — a description this user corrected, within edit distance
    4. purpose          — app/domain/payment_taxonomy.py recognised what the payment was for
    5. default          — the discretionary fallback, at low confidence, flagged for review

Step 4 sits below the user's own corrections deliberately. The purpose taxonomy is a
shipped generalisation about what a merchant sells; a correction is this user saying what
this payment was. Where they disagree, the user is right about their own money. It sits
above the default because "we recognised this as a rent debit order" is a real finding and
filing it as discretionary spending would be a lie of omission.

Similarity is edit distance (app/domain/text_match.py), not `difflib.SequenceMatcher` as
it once was — see that module for why a metric matters when a single threshold is applied
in three different places.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.domain.payment_taxonomy import (
    PURPOSE_CATEGORY_NAME,
    PURPOSE_KIND,
    SpendingPurpose,
    classify_payment,
)
from app.domain.text_match import description_similarity
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

# Whole-word match around a category name. Built as a format string rather than an
# f-string literal so the backslash escapes stay readable next to the escaped name.
_WORD_BOUNDARY = r"(?<![a-z0-9]){name}(?![a-z0-9])"


def _rule_match(normalised_description: str, categories: list[Category]) -> Category | None:
    """The most specific category whose name appears as a whole word in the description.

    Two things here are not obvious.

    Word boundaries, not substrings. The previous `name.lower() in description` test
    matched "Rent" inside "current account fee", which with the system categories now
    seeded (app/services/category_seed.py) would have filed every monthly account fee as
    rent — the single largest line in most budgets, invented out of a substring.

    Longest name first. "Vehicle instalment" and "Insurance" can both appear in one
    description; the longer name is the more specific statement about it, and matching on
    dictionary order instead would make the answer depend on which category happened to be
    created first.
    """
    best: Category | None = None
    for category in categories:
        name = category.name.lower().strip()
        if not name:
            continue
        if not re.search(_WORD_BOUNDARY.format(name=re.escape(name)), normalised_description):
            continue
        if best is None or len(name) > len(best.name):
            best = category
    return best


@dataclass(frozen=True, slots=True)
class CategorySuggestion:
    category: Category | None
    confidence: Decimal
    # "rule" | "correction_exact" | "correction_similar" | "purpose" | "default" | "none"
    basis: str


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
        amount: Decimal | None = None,
    ) -> CategorySuggestion:
        """Choose a category for one description, with the confidence and why.

        Pure given its arguments — the caller loads `categories` and `corrections` once
        per import rather than once per row, which is what keeps a 10,000-row file inside
        the spec's performance criterion.

        `amount` is optional only so the existing callers that have no amount to give (a
        rule-only re-run) keep working. Without it the purpose step is skipped entirely,
        because the taxonomy's income/expense rules are decided by the sign and guessing
        the sign would be worse than not classifying.
        """
        by_id = {c.id: c for c in categories}

        rule_match = _rule_match(normalised_description, categories)
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
            score = description_similarity(description, normalised_description)
            if score > best_score:
                best_score = score
                best_id = category_id
        if best_id is not None and best_score >= Decimal(str(SIMILARITY_THRESHOLD)):
            if best_id in by_id:
                # Confidence IS the similarity: a 0.83 match is a weaker claim than a
                # 0.97 one, and storing both as the same number would throw away the only
                # information a reviewer has about which suggestions to check.
                return CategorySuggestion(by_id[best_id], best_score, "correction_similar")

        if amount is not None:
            purpose_match = self._suggest_from_purpose(
                normalised_description=normalised_description,
                categories=categories,
                amount=amount,
            )
            if purpose_match is not None:
                return purpose_match

        fallback = next(
            (c for c in categories if c.kind is CategoryKind.DISCRETIONARY), None
        )
        if fallback is None:
            return CategorySuggestion(None, Decimal("0"), "none")
        return CategorySuggestion(fallback, CONFIDENCE_DEFAULT, "default")

    def _suggest_from_purpose(
        self,
        *,
        normalised_description: str,
        categories: list[Category],
        amount: Decimal,
    ) -> CategorySuggestion | None:
        """Map a detected spending purpose onto one of this user's categories.

        The match is on the canonical category name for the purpose, then on kind if that
        name does not exist. Falling back to kind matters for a user who renamed
        "Groceries" to "Food" — the purpose is still essential spending, and filing it as
        essential under a differently named category is right, while filing it as
        discretionary because the name did not match is wrong.

        Returns None when neither lookup finds a category, leaving the caller's default to
        run. An unrecognised purpose never invents a category.
        """
        classification = classify_payment(description=normalised_description, amount=amount)
        if classification.purpose is SpendingPurpose.UNKNOWN:
            return None

        wanted_name = PURPOSE_CATEGORY_NAME[classification.purpose].lower()
        by_name = next((c for c in categories if c.name.lower() == wanted_name), None)
        if by_name is not None:
            return CategorySuggestion(by_name, classification.purpose_confidence, "purpose")

        wanted_kind = PURPOSE_KIND[classification.purpose].value
        by_kind = next((c for c in categories if c.kind.value == wanted_kind), None)
        if by_kind is None:
            return None
        # A kind-only match is a weaker claim than a name match, and the stored confidence
        # has to say so or a reviewer cannot tell the two apart.
        return CategorySuggestion(
            by_kind, classification.purpose_confidence / 2, "purpose"
        )

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
                amount=txn.amount,
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
