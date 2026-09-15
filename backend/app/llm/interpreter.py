"""The interpretation-layer interface. See ADR-002 and docs/architecture.md §3.6.

The model receives an already-computed result and turns it into language. It never
computes, never queries, and never writes. `NullInterpreter` is what the app runs by
default: the API returns figures with `answer: null, narration_available: false`, per
requirement 12 — the system must remain usable with the model unavailable.

`build_narration_payload` is the prompt contract, and it is a whitelist rather than a
filter. Only computed figures and the user's own question reach the provider. No
transaction description, merchant name, account number or free-text field is ever
included, which is what makes prompt injection through an imported statement structurally
impossible rather than merely unlikely: the text never reaches the prompt, and the figures
were computed before narration was asked for, so nothing the provider returns can change
them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# The only keys a figure may contribute to a prompt. Anything else on a figure object —
# and any future field added to one — is dropped rather than forwarded.
FIGURE_PROMPT_KEYS = ("label", "value", "unit", "source")

RESPONSE_CONSTRAINTS = (
    "Use only the figures given. Do not compute, estimate, or infer any number. "
    "Do not state or imply financial advice: describe what the figures are, not what "
    "the reader should do. If a figure is not present, say it is not available rather "
    "than supplying one."
)


@dataclass(frozen=True, slots=True)
class NarrationPayload:
    question: str
    figures: tuple[dict[str, str], ...]
    constraints: str = RESPONSE_CONSTRAINTS


def build_narration_payload(*, question: str, figures: list[dict]) -> NarrationPayload:
    """Assemble exactly what may be sent to the provider, and nothing else.

    "Only the minimum financial context required is sent to the provider"
    (specs/ai-cfo.md). The question is included because the narration has to answer it;
    the figures are included as label/value/unit/source only, so a `result_id` or an
    internal reference never leaves the system either.
    """
    whitelisted = tuple(
        {key: str(figure[key]) for key in FIGURE_PROMPT_KEYS if key in figure}
        for figure in figures
    )
    return NarrationPayload(question=question, figures=whitelisted)


class Interpreter(Protocol):
    def narrate(self, *, payload: NarrationPayload) -> str | None: ...


class NullInterpreter:
    """The default. Returns no narration, so the client renders the figures unnarrated.

    This is the provider-unavailable path made permanent, and having it as the default
    means that path is exercised constantly rather than only during an outage.
    """

    def narrate(self, *, payload: NarrationPayload) -> str | None:
        return None
