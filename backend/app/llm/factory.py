"""Which interpreter the request path gets. See ADR-002.

One place decides, so no call site has to know whether a provider is configured. With no
`OPENAI_API_KEY` the answer is `NullInterpreter`, which is the default the product is
developed and tested against — the provider is an enhancement to a response that is
already complete without it.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.llm.interpreter import Interpreter, NullInterpreter

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _cached_interpreter(
    api_key: str, model: str, base_url: str, timeout_seconds: float
) -> Interpreter:
    """Built once per process. The SDK client holds a connection pool, so constructing one
    per request would pay a new TLS handshake for every question asked.
    """
    if not api_key:
        return NullInterpreter()

    from app.llm.openai_interpreter import OpenAIInterpreter, build_openai_client

    try:
        client = build_openai_client(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            base_url=base_url or None,
        )
    except Exception:
        # A provider that cannot even be constructed must not take the endpoint with it:
        # the figures are still computable, so fall back to the documented no-narration
        # response rather than failing the request.
        logger.warning("narration provider unavailable; falling back to figures only", exc_info=True)
        return NullInterpreter()

    return OpenAIInterpreter(client=client, model=model)


def build_interpreter() -> Interpreter:
    from flask import current_app

    config = current_app.config
    return _cached_interpreter(
        config.get("OPENAI_API_KEY", ""),
        config.get("OPENAI_MODEL", "gpt-4o-mini"),
        config.get("OPENAI_BASE_URL", ""),
        float(config.get("OPENAI_TIMEOUT_SECONDS", 8)),
    )
