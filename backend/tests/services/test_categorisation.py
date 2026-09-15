"""CategorisationService.suggest — pure given its arguments, so no database needed.

Covers the precedence specs/transactions.md step 5 requires: rules first, then similarity
against the user's own corrected history, then a default with low confidence.
"""

from decimal import Decimal
from uuid import uuid4

from app.models.category import Category, CategoryKind
from app.services.categorisation import (
    CONFIDENCE_DEFAULT,
    CONFIDENCE_EXACT_CORRECTION,
    CONFIDENCE_RULE,
    CategorisationService,
)


def _category(name: str, kind: CategoryKind) -> Category:
    category = Category(name=name, kind=kind)
    category.id = uuid4()
    return category


GROCERIES = _category("Groceries", CategoryKind.ESSENTIAL)
DINING = _category("Dining", CategoryKind.DISCRETIONARY)
FUEL = _category("Fuel", CategoryKind.ESSENTIAL)
CATEGORIES = [GROCERIES, DINING, FUEL]


def _service() -> CategorisationService:
    # `suggest` touches no session; passing None documents that and would fail loudly
    # if that ever stopped being true.
    return CategorisationService(None)  # type: ignore[arg-type]


def test_a_rule_match_wins_and_is_high_confidence() -> None:
    suggestion = _service().suggest(
        normalised_description="checkers groceries sandton",
        categories=CATEGORIES,
        corrections={},
    )

    assert suggestion.category is GROCERIES
    assert suggestion.basis == "rule"
    assert suggestion.confidence == CONFIDENCE_RULE


def test_an_exact_correction_is_used_when_no_rule_matches() -> None:
    suggestion = _service().suggest(
        normalised_description="woolies claremont",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )

    assert suggestion.category is GROCERIES
    assert suggestion.basis == "correction_exact"
    assert suggestion.confidence == CONFIDENCE_EXACT_CORRECTION


def test_a_rule_still_beats_a_correction_for_a_different_merchant() -> None:
    """Precedence is rules first — a correction about one merchant must not override an
    explicit rule match on another.
    """
    suggestion = _service().suggest(
        normalised_description="shell fuel garage",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )

    assert suggestion.category is FUEL
    assert suggestion.basis == "rule"


def test_a_similar_description_inherits_the_corrected_category() -> None:
    """The same merchant at a different branch: one correction should teach the system
    about both.
    """
    suggestion = _service().suggest(
        normalised_description="woolies claremont mall",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )

    assert suggestion.category is GROCERIES
    assert suggestion.basis == "correction_similar"
    assert Decimal("0.82") <= suggestion.confidence < Decimal("1")


def test_confidence_reflects_how_similar_the_match_was() -> None:
    service = _service()
    close = service.suggest(
        normalised_description="woolies claremont mal",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )
    exact = service.suggest(
        normalised_description="woolies claremont",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )

    assert close.confidence < exact.confidence


def test_an_unrelated_description_does_not_inherit_a_correction() -> None:
    """Two merchants sharing a word are not the same merchant; inheriting here would be
    a guess dressed up as knowledge.
    """
    suggestion = _service().suggest(
        normalised_description="netflix subscription",
        categories=CATEGORIES,
        corrections={"woolies claremont": GROCERIES.id},
    )

    assert suggestion.basis == "default"
    assert suggestion.category is DINING  # the discretionary fallback
    assert suggestion.confidence == CONFIDENCE_DEFAULT


def test_the_default_is_low_confidence_so_it_can_be_reviewed() -> None:
    suggestion = _service().suggest(
        normalised_description="unknown merchant 12345",
        categories=CATEGORIES,
        corrections={},
    )

    assert suggestion.confidence == CONFIDENCE_DEFAULT
    assert suggestion.confidence < CONFIDENCE_RULE


def test_no_categories_at_all_yields_no_suggestion_rather_than_a_crash() -> None:
    suggestion = _service().suggest(
        normalised_description="anything", categories=[], corrections={}
    )

    assert suggestion.category is None
    assert suggestion.basis == "none"


def test_a_correction_pointing_at_a_deleted_category_falls_through() -> None:
    """A correction naming a category that no longer exists must not resurrect it."""
    suggestion = _service().suggest(
        normalised_description="woolies claremont",
        categories=CATEGORIES,
        corrections={"woolies claremont": uuid4()},
    )

    assert suggestion.basis == "default"
