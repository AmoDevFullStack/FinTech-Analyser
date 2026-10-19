"""Description matching by edit distance. Pure, stdlib-only, deterministic.

Bank statement descriptions for the same merchant are never byte-identical. "WOOLWORTHS
CLAREMONT", "WOOLWORTHS SEA POINT" and "WOOLWORTHS CLAREMNT" are one merchant with three
spellings, and a search or a categorisation that only does substring matching finds one
of the three. This module is the shared answer to "are these two descriptions the same
thing", used by search (app/repositories/transaction.py), categorisation
(app/services/categorisation.py) and probable-duplicate detection
(app/services/import_service.py) so all three agree.

It lives in `app/domain/` rather than `app/core/` because the engines here may not import
upward: `payment_taxonomy` depends on it, and a domain module importing from `core` would
break the rule that `app/domain/` imports nothing but stdlib and its own siblings. No
money is calculated here.

Why Levenshtein rather than `difflib.SequenceMatcher`, which this code replaced:
SequenceMatcher's ratio is built on longest-matching-block recursion, which is neither a
metric nor stable under small edits — inserting one character can move the ratio more than
deleting three. Edit distance is a true metric, so a threshold means the same thing
everywhere it is applied, and the distance itself is explainable to a user ("three
characters different").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

RATIO_PLACES = Decimal("0.000001")

# Two tokens count as "the same word" at or above this. One transposition in a nine-letter
# merchant name (claremont / claremnot) scores 0.778; two unrelated seven-letter words
# (woolies / netflix) score 0.143. The gap between those is wide, and 0.75 sits in it.
TOKEN_MATCH_THRESHOLD = Decimal("0.75")

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def levenshtein_distance(a: str, b: str) -> int:
    """Minimum single-character insertions, deletions, and substitutions turning `a` into `b`.

    Formula:
        The standard Wagner-Fischer dynamic program, carrying one row rather than the full
        matrix:
            d[0][j] = j, d[i][0] = i
            d[i][j] = min(d[i-1][j] + 1,                            # deletion
                          d[i][j-1] + 1,                            # insertion
                          d[i-1][j-1] + (a[i-1] != b[j-1]))         # substitution

    Assumptions:
        - Comparison is on the strings exactly as given. Callers wanting case- or
          punctuation-insensitivity normalise first; `description_similarity` does.
        - A transposition is two edits, not one (Levenshtein, not Damerau-Levenshtein).
          Keeping it pure Levenshtein preserves the triangle inequality, which is what
          lets one threshold be reasoned about across all three call sites.

    Rounding:
        None — the result is an exact count.

    Raises:
        Nothing. Every pair of strings has a distance, including empty ones.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if ca == cb else 1),
                )
            )
        previous = current
    return previous[-1]


def levenshtein_ratio(a: str, b: str) -> Decimal:
    """Similarity of two strings in [0, 1], as one minus the normalised edit distance.

    Formula:
        ratio = 1 - levenshtein_distance(a, b) / max(len(a), len(b))

    Assumptions:
        - Two empty strings are defined as identical (1). The alternative is a division by
          zero, and no caller means "unlike" by comparing nothing to nothing.
        - Normalising by the longer string is what makes the ratio penalise a length
          difference. Use `description_similarity` instead when a trailing branch name
          should not count as a mismatch.

    Rounding:
        Six places, ROUND_HALF_UP, matching the NUMERIC(9,6) that a confidence derived from
        this is stored in.

    Raises:
        Nothing.
    """
    if not a and not b:
        return Decimal("1.000000")
    longest = max(len(a), len(b))
    distance = Decimal(levenshtein_distance(a, b))
    return (Decimal("1") - distance / Decimal(longest)).quantize(
        RATIO_PLACES, rounding=ROUND_HALF_UP
    )


def tokenise(value: str) -> list[str]:
    """Lower-case alphanumeric runs, in order. Punctuation and whitespace are separators."""
    return _TOKEN_PATTERN.findall(value.lower())


def description_similarity(a: str, b: str) -> Decimal:
    """Similarity of two transaction descriptions in [0, 1], token-aware.

    Formula:
        Each token of `a` is greedily paired with its best-scoring unused token in `b`,
        scored by `levenshtein_ratio`. A pair below TOKEN_MATCH_THRESHOLD is discarded
        rather than partially credited. The result is a Sorensen-Dice ratio over the
        characters those accepted pairs account for:

            matched    = sum(ratio(x, y) * (len(x) + len(y)) for each accepted pair)
            similarity = matched / (characters in a's tokens + characters in b's tokens)

    Assumptions:
        - Whole-string edit distance is the wrong measure for merchant descriptions:
          "woolworths claremont" against "woolworths claremont mall" scores 1 - 5/25 = 0.80
          on a raw ratio, below any threshold that also rejects genuinely different
          merchants. Under the Dice form the same pair scores 0.889, because the extra
          token costs only its own length instead of dragging down every matched
          character with it.
        - Greedy pairing, not optimal assignment. Descriptions are short and their tokens
          are rarely near-duplicates of one another, so the Hungarian algorithm would cost
          more than it would change.
        - Identical strings score exactly 1.
        - Token order is ignored: "capitec eft nadia" and "eft nadia capitec" are the same
          payment described by two exports of the same statement.

    Rounding:
        Six places, ROUND_HALF_UP.

    Raises:
        Nothing. A description with no alphanumeric content scores 0 against anything.
    """
    tokens_a = tokenise(a)
    tokens_b = tokenise(b)
    if not tokens_a or not tokens_b:
        return Decimal("0.000000")

    total = Decimal(sum(len(t) for t in tokens_a) + sum(len(t) for t in tokens_b))
    unused = list(tokens_b)
    matched = Decimal("0")

    for token in tokens_a:
        best_index = -1
        best_ratio = Decimal("0")
        for index, candidate in enumerate(unused):
            ratio = levenshtein_ratio(token, candidate)
            if ratio > best_ratio:
                best_index, best_ratio = index, ratio
        if best_index >= 0 and best_ratio >= TOKEN_MATCH_THRESHOLD:
            partner = unused.pop(best_index)
            matched += best_ratio * Decimal(len(token) + len(partner))

    return (matched / total).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Match:
    """One candidate and how well it matched, with which rule decided that.

    `basis` is "exact" for a case-insensitive substring hit and "fuzzy" for an
    edit-distance one. A caller showing results to a user needs the difference: "contains
    what you typed" and "looks like what you typed" are different claims.
    """

    key: str
    score: Decimal
    basis: str


def rank_matches(
    *,
    query: str,
    candidates: dict[str, str],
    threshold: Decimal,
) -> list[Match]:
    """Rank candidate descriptions against a search query, best first.

    Formula:
        A candidate containing the query as a case-insensitive substring scores 1 with
        basis "exact". Every other candidate scores `description_similarity` with basis
        "fuzzy", and is dropped below `threshold`.

    Assumptions:
        - `candidates` maps an opaque key (a transaction id rendered as a string, in
          practice) to the text to match against. Keys are returned, not the text, so the
          caller decides what a result is.
        - Ties keep the caller's insertion order, so for a date-ordered candidate map the
          more recent of two equally good matches is listed first.
        - An empty query matches nothing rather than everything: "results for no search
          term" is the unfiltered list, which is the caller's other code path.

    Rounding:
        Scores are already six-place Decimals from `description_similarity`.

    Raises:
        ValueError: if threshold is outside [0, 1].
    """
    if threshold < 0 or threshold > 1:
        raise ValueError(f"threshold must be within [0, 1], got {threshold}")
    if not query.strip():
        return []

    needle = query.strip().lower()
    matches: list[Match] = []
    for key, text in candidates.items():
        haystack = text.lower()
        if needle in haystack:
            matches.append(Match(key=key, score=Decimal("1.000000"), basis="exact"))
            continue
        score = description_similarity(needle, haystack)
        if score >= threshold:
            matches.append(Match(key=key, score=score, basis="fuzzy"))

    return sorted(matches, key=lambda m: -m.score)
