"""The OpenAI narration provider. See ADR-002, specs/ai-cfo.md, and `interpreter.py`.

This is an `Interpreter`, which means it does exactly one thing: turn an
already-computed `NarrationPayload` into a sentence. It does not classify, does not
choose an engine, does not see a transaction description, and cannot change a figure —
`build_narration_payload` has already reduced the prompt to the question plus
label/value/unit/source, and this module never reaches past that payload.

Every failure returns None rather than raising. None is not an error path here: it is the
documented `narration_available: false` response the client already renders, so an outage,
a rate limit, a timeout, or a malformed reply all degrade to "figures without prose",
which is the product working as designed rather than the product being down.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.llm.interpreter import NarrationPayload

logger = logging.getLogger(__name__)

# What the model is. Restated in the instructions rather than only in the payload because
# the payload is data and this is the role: the constraints in RESPONSE_CONSTRAINTS say
# what it may not do, and this says what it is for.
SYSTEM_INSTRUCTIONS = (
    "You are the narration layer of a personal-finance app. Each request gives you a "
    "question, zero or more figures, and a constraints string that governs how to reply — "
    "follow the constraints exactly. When figures are given, they were computed by a "
    "deterministic engine and are already correct: say what they mean in plain language, "
    "quoting them exactly as given, including their units, and never introduce a number "
    "that is not in the figures. When no figures are given, the constraints describe a "
    "non-financial reply instead, such as a greeting. Write in South African English, "
    "address the reader as 'you', and use at most three sentences."
)


@dataclass(frozen=True, slots=True)
class OpenAIInterpreter:
    """Narrates a payload with OpenAI's Responses API.

    `max_output_tokens` is a hard cap rather than a suggestion: narration that runs long
    is narration that has started reasoning, and the interface has room for a paragraph.
    """

    client: object
    model: str
    max_output_tokens: int = 320

    def narrate(self, *, payload: NarrationPayload) -> str | None:
        prompt = json.dumps(
            {
                "question": payload.question,
                "figures": [dict(figure) for figure in payload.figures],
                "constraints": payload.constraints,
            },
            ensure_ascii=False,
        )

        try:
            response = self.client.responses.create(  # type: ignore[attr-defined]
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
            )
        except Exception:
            # Deliberately broad: the provider SDK raises for connection, auth, rate
            # limit, timeout and content-filter cases, and the answer to every one of
            # them here is the same — return the figures unnarrated. Logged at warning
            # so an outage is visible in the logs without becoming a 500 for the reader.
            logger.warning("narration provider call failed; returning figures only", exc_info=True)
            return None

        text = getattr(response, "output_text", None)
        if not isinstance(text, str):
            return None
        text = text.strip()
        return text or None


def build_openai_client(*, api_key: str, timeout_seconds: float, base_url: str | None = None):
    """Construct the SDK client, importing the SDK only when a key is configured.

    The import is local so the package stays an optional dependency at runtime: a
    deployment with no key configured never imports it, and `NullInterpreter` remains the
    default the app is developed against.
    """
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout_seconds, base_url=base_url)
