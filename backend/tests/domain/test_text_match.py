"""Edit-distance matching. Pure, so no database.

The distances asserted below are hand-computed and the working is recorded with each one,
since a test that asserts what the function returns proves nothing about whether the
function is right.
"""

from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from app.domain.text_match import (
    TOKEN_MATCH_THRESHOLD,
    description_similarity,
    levenshtein_distance,
    levenshtein_ratio,
    rank_matches,
    tokenise,
)


# --------------------------------------------------------------------------------------
# Distance
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b", "expected", "working"),
    [
        ("kitten", "sitting", 3, "k->s, e->i, +g — the textbook example"),
        ("woolworths", "woolworths", 0, "identical"),
        ("", "spar", 4, "four insertions"),
        ("spar", "", 4, "four deletions"),
        ("claremont", "claremnot", 2, "o->n and n->o; a transposition is two edits"),
        ("checkers", "chekers", 1, "one deletion"),
        ("uber", "uber eats", 5, "five insertions: space + e,a,t,s"),
    ],
)
def test_distance_matches_hand_computed_values(a, b, expected, working) -> None:
    assert levenshtein_distance(a, b) == expected, working


def test_distance_is_symmetric() -> None:
    assert levenshtein_distance("engen", "engon") == levenshtein_distance("engon", "engen")


@given(st.text(max_size=12), st.text(max_size=12), st.text(max_size=12))
def test_distance_obeys_the_triangle_inequality(a: str, b: str, c: str) -> None:
    """The property the whole design rests on: because this is a metric, one threshold
    means the same thing at all three call sites that apply it."""
    assert levenshtein_distance(a, c) <= levenshtein_distance(a, b) + levenshtein_distance(b, c)


@given(st.text(max_size=20), st.text(max_size=20))
def test_distance_is_bounded_by_the_longer_string(a: str, b: str) -> None:
    assert levenshtein_distance(a, b) <= max(len(a), len(b))


# --------------------------------------------------------------------------------------
# Ratio
# --------------------------------------------------------------------------------------
def test_ratio_of_identical_strings_is_one() -> None:
    assert levenshtein_ratio("woolworths", "woolworths") == Decimal("1.000000")


def test_ratio_of_two_empty_strings_is_one() -> None:
    """Defined rather than a division by zero. No caller means "unlike" by comparing
    nothing to nothing."""
    assert levenshtein_ratio("", "") == Decimal("1.000000")


def test_ratio_normalises_by_the_longer_string() -> None:
    """1 - 1/8 = 0.875, by hand: one deletion out of an eight-character longer string."""
    assert levenshtein_ratio("checkers", "chekers") == Decimal("0.875000")


@given(st.text(max_size=20), st.text(max_size=20))
def test_ratio_stays_within_zero_and_one(a: str, b: str) -> None:
    ratio = levenshtein_ratio(a, b)
    assert Decimal("0") <= ratio <= Decimal("1")


# --------------------------------------------------------------------------------------
# Description similarity
# --------------------------------------------------------------------------------------
def test_tokenise_drops_punctuation_and_lowercases() -> None:
    assert tokenise("POS PURCH #4471 Woolworths, Claremont") == [
        "pos",
        "purch",
        "4471",
        "woolworths",
        "claremont",
    ]


def test_identical_descriptions_score_one() -> None:
    assert description_similarity("woolworths claremont", "woolworths claremont") == Decimal(
        "1.000000"
    )


def test_an_extra_branch_token_costs_only_its_own_length() -> None:
    """The case raw edit distance gets wrong, and the reason the Dice form exists.

    Hand-computed: tokens are (woolworths, claremont) against (woolworths, claremont, mall).
    Both pairs match exactly, contributing 1 * (10+10) + 1 * (9+9) = 38 characters.
    The denominator is 19 + 23 = 42. 38/42 = 0.904762.

    A raw `levenshtein_ratio` on the same pair gives 1 - 5/25 = 0.80, which sits below any
    threshold that still rejects genuinely different merchants.
    """
    score = description_similarity("woolworths claremont", "woolworths claremont mall")
    assert score == Decimal("0.904762")
    assert levenshtein_ratio("woolworths claremont", "woolworths claremont mall") == Decimal(
        "0.800000"
    )


def test_two_different_merchants_sharing_nothing_score_zero() -> None:
    assert description_similarity("netflix subscription", "woolworths claremont") == Decimal(
        "0.000000"
    )


def test_token_order_is_ignored() -> None:
    """Two exports of the same statement can order the same three tokens differently."""
    assert description_similarity(
        "capitec eft nadia", "nadia capitec eft"
    ) == Decimal("1.000000")


def test_a_misspelled_merchant_still_matches() -> None:
    """The case the search box exists for: a user who cannot spell what their bank prints."""
    assert description_similarity("woolwrths claremnt", "woolworths claremont") >= Decimal(
        "0.85"
    )


def test_a_description_with_no_letters_or_digits_scores_zero() -> None:
    assert description_similarity("---", "woolworths") == Decimal("0.000000")


def test_a_token_below_the_threshold_contributes_nothing() -> None:
    """Partial credit for a near-miss token is deliberately not given: it is what lets a
    long shared prefix drag two unrelated merchants over the line."""
    assert TOKEN_MATCH_THRESHOLD == Decimal("0.75")
    assert description_similarity("spar", "shell") == Decimal("0.000000")


# --------------------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------------------
def test_a_substring_hit_scores_one_and_is_marked_exact() -> None:
    matches = rank_matches(
        query="woolworths",
        candidates={"a": "pos purchase woolworths claremont"},
        threshold=Decimal("0.6"),
    )
    assert len(matches) == 1
    assert matches[0].score == Decimal("1.000000")
    assert matches[0].basis == "exact"


def test_an_exact_hit_outranks_a_fuzzy_one() -> None:
    matches = rank_matches(
        query="woolworths",
        candidates={"fuzzy": "woolwrths sea point", "exact": "woolworths claremont"},
        threshold=Decimal("0.6"),
    )
    assert [m.key for m in matches] == ["exact", "fuzzy"]
    assert matches[1].basis == "fuzzy"


def test_candidates_below_the_threshold_are_dropped() -> None:
    matches = rank_matches(
        query="woolworths",
        candidates={"a": "engen garage rondebosch"},
        threshold=Decimal("0.6"),
    )
    assert matches == []


def test_an_empty_query_matches_nothing() -> None:
    """"Results for no search term" is the unfiltered list, which is the caller's other
    code path — not every row at score 1."""
    assert rank_matches(query="   ", candidates={"a": "anything"}, threshold=Decimal("0.6")) == []


@pytest.mark.parametrize("threshold", [Decimal("-0.01"), Decimal("1.01")])
def test_a_threshold_outside_zero_to_one_is_rejected(threshold: Decimal) -> None:
    with pytest.raises(ValueError, match="threshold"):
        rank_matches(query="x", candidates={}, threshold=threshold)
