"""The interpretation-layer interface. See ADR-002 and docs/architecture.md §3.6.

Out of scope for this "Now" slice (PLAN.md defers the AI CFO to Next) — this stub exists
so the boundary is real code, not just a document, and so a future implementation has
something concrete to satisfy. `NullInterpreter` is what the app runs today: the API
returns figures with `answer: null, narration_available: false`, per requirement 12 —
the system must remain usable with the model unavailable.
"""

from __future__ import annotations

from typing import Protocol


class Interpreter(Protocol):
    def narrate(self, *, figures: list[dict]) -> str | None: ...


class NullInterpreter:
    def narrate(self, *, figures: list[dict]) -> str | None:
        return None
