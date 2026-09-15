"""Intent classification and parameter extraction. See specs/ai-cfo.md steps 1 and 2.

ADR-002 permits the model to classify intent. This implementation does not use it, and
that is a deliberate choice rather than an unfinished one: classification decides which
engine runs, so a non-deterministic classifier makes the same question answerable
differently on two days. Rules are testable, reproducible, and cheap, and when they fail
they fail into `UNSUPPORTED`, which is a recoverable answer — "I can't model that yet" —
rather than a confident wrong one.

Nothing here touches money arithmetic; it only reads figures out of a sentence. The
figures it extracts are inputs to an engine, never results.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# "R15,000", "R15 000", "R15000.50", "15000 rand", "15k"
_AMOUNT_PATTERN = re.compile(
    r"(?:r\s*)?(\d[\d\s,]*(?:\.\d{1,2})?)\s*(k\b|thousand\b|rand\b)?", re.IGNORECASE
)
_MONTH_PATTERN = re.compile("|".join(MONTHS), re.IGNORECASE)
_HORIZON_PATTERN = re.compile(r"(\d+)\s*(month|year)s?", re.IGNORECASE)


class Capability(str, enum.Enum):
    AFFORDABILITY_CHECK = "affordability_check"
    SCENARIO_REQUEST = "scenario_request"
    POSITION_QUERY = "position_query"
    SPENDING_ANALYSIS = "spending_analysis"
    DEBT_QUESTION = "debt_question"
    GOAL_QUESTION = "goal_question"
    FORECAST_QUESTION = "forecast_question"
    FIGURE_EXPLANATION = "figure_explanation"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ExtractedParameters:
    amount: Decimal | None = None
    month: int | None = None
    year: int | None = None
    horizon_months: int | None = None


@dataclass(frozen=True, slots=True)
class Intent:
    capability: Capability
    parameters: ExtractedParameters
    missing_parameters: tuple[str, ...] = field(default_factory=tuple)
    matched_on: str = ""

    @property
    def is_supported(self) -> bool:
        return self.capability is not Capability.UNSUPPORTED

    @property
    def needs_clarification(self) -> bool:
        return bool(self.missing_parameters)


# Ordered: the first capability whose phrases appear wins, so a question containing both
# "afford" and "spend" is treated as an affordability check, which is the stronger signal.
_CAPABILITY_PHRASES: tuple[tuple[Capability, tuple[str, ...]], ...] = (
    (
        Capability.AFFORDABILITY_CHECK,
        ("can i afford", "could i afford", "afford", "affordable", "can i buy"),
    ),
    (
        Capability.SCENARIO_REQUEST,
        ("what if", "what happens if", "if i buy", "if i take", "simulate", "model "),
    ),
    (
        Capability.DEBT_QUESTION,
        ("debt", "loan", "instalment", "installment", "repay", "pay off", "interest"),
    ),
    (
        Capability.GOAL_QUESTION,
        ("goal", "saving for", "save for", "target date", "on track"),
    ),
    (
        Capability.FORECAST_QUESTION,
        ("forecast", "projection", "project", "next year", "in 12 months", "by 2027"),
    ),
    (
        Capability.SPENDING_ANALYSIS,
        ("spend", "spending", "spent", "where is my money", "categories", "budget"),
    ),
    (
        Capability.POSITION_QUERY,
        ("net worth", "how much do i have", "balance", "savings", "position", "worth"),
    ),
    (
        Capability.FIGURE_EXPLANATION,
        ("why is", "why did", "how is that", "explain", "what does that mean", "how did you"),
    ),
)

# Which parameters a capability cannot run without. Anything absent here is optional and,
# where the engine needs a default, that default is stated in the response rather than
# silently assumed — per specs/ai-cfo.md: "Where a required parameter is missing, ask for
# it rather than assuming."
_REQUIRED_PARAMETERS: dict[Capability, tuple[str, ...]] = {
    Capability.AFFORDABILITY_CHECK: ("amount",),
    Capability.SCENARIO_REQUEST: ("amount",),
}


def extract_parameters(question: str, *, as_of: date | None = None) -> ExtractedParameters:
    """Pull the amount, month and horizon out of a question.

    An amount written "15k" or "15 thousand" is multiplied out; thousands separators and
    the rand symbol are stripped. Only the first amount is taken — a question containing
    two figures is ambiguous, and guessing which one is the subject would be exactly the
    assuming the spec forbids.

    `as_of` resolves a bare month name to a year: a month already past this year is read
    as next year, since "in December" asked in January means this December, but asked in
    December means the one coming.
    """
    amount = None
    for raw, suffix in _AMOUNT_PATTERN.findall(question):
        cleaned = raw.replace(" ", "").replace(",", "").strip()
        if not cleaned or cleaned == ".":
            continue
        try:
            value = Decimal(cleaned)
        except InvalidOperation:
            continue
        if suffix and suffix.lower().startswith(("k", "thousand")):
            value *= Decimal("1000")
        elif value < 100:
            # A bare small number is a count ("3 months", "2 goals"), not an amount.
            continue
        amount = value
        break

    month = None
    year = None
    month_match = _MONTH_PATTERN.search(question)
    if month_match:
        month = MONTHS[month_match.group(0).lower()]
        reference = as_of or date.today()
        year = reference.year if month >= reference.month else reference.year + 1

    horizon_months = None
    horizon_match = _HORIZON_PATTERN.search(question)
    if horizon_match:
        count = int(horizon_match.group(1))
        horizon_months = count * 12 if horizon_match.group(2).lower() == "year" else count

    return ExtractedParameters(
        amount=amount, month=month, year=year, horizon_months=horizon_months
    )


def classify(question: str, *, as_of: date | None = None) -> Intent:
    """Map a question to a supported capability, or to `UNSUPPORTED`.

    Returns the missing required parameters rather than filling them in, so the caller can
    ask a clarifying question. A question matching no capability returns `UNSUPPORTED` with
    no parameters — the system says what it cannot model instead of approximating.
    """
    lowered = question.lower().strip()
    parameters = extract_parameters(question, as_of=as_of)

    for capability, phrases in _CAPABILITY_PHRASES:
        for phrase in phrases:
            if phrase in lowered:
                required = _REQUIRED_PARAMETERS.get(capability, ())
                missing = tuple(
                    name for name in required if getattr(parameters, name, None) is None
                )
                return Intent(
                    capability=capability,
                    parameters=parameters,
                    missing_parameters=missing,
                    matched_on=phrase,
                )

    return Intent(capability=Capability.UNSUPPORTED, parameters=parameters)


def clarifying_question(intent: Intent) -> str | None:
    """The question to ask back when a required parameter is missing."""
    if not intent.needs_clarification:
        return None
    if "amount" in intent.missing_parameters:
        return "How much is it? I need the amount before I can work out what it costs you."
    names = ", ".join(intent.missing_parameters)
    return f"I need {names} before I can answer that."


def unsupported_explanation(intent: Intent) -> str:
    """What the system cannot yet model, stated plainly.

    specs/ai-cfo.md: unsupported questions "say so and name what is missing".
    """
    supported = ", ".join(
        c.value.replace("_", " ")
        for c in Capability
        if c is not Capability.UNSUPPORTED
    )
    return (
        "I can't model that question yet. I can answer questions about: "
        f"{supported}. I don't estimate answers outside those, because an estimate here "
        "would look exactly like a calculation."
    )
