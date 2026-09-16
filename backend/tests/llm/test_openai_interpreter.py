"""The narration provider's contract: it narrates, it leaks nothing, and it never raises.

No test here touches the network. The SDK client is a stand-in that records what it was
asked to send, which is the only way to assert the prompt-whitelist property — the point
of ADR-002 is what does NOT reach the provider, and that can only be checked by looking at
the outgoing request.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.llm.interpreter import build_narration_payload
from app.llm.openai_interpreter import OpenAIInterpreter


class RecordingClient:
    def __init__(self, *, output_text: str | None = "Your emergency fund covers 0.90 months."):
        self.calls: list[dict] = []
        self._output_text = output_text
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self._output_text)


class ExplodingClient:
    def __init__(self, error: Exception):
        self._error = error
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        raise self._error


def _payload(question: str = "Can I afford a R15,000 holiday in December?"):
    return build_narration_payload(
        question=question,
        figures=[
            {
                "label": "Emergency fund after",
                "value": "0.90",
                "unit": "months",
                "source": "emergency_fund_engine",
                "result_id": "0192f0c1-0000-7000-8000-000000000001",
            }
        ],
    )


def test_narrates_the_provider_reply() -> None:
    client = RecordingClient()
    interpreter = OpenAIInterpreter(client=client, model="gpt-4o-mini")

    assert interpreter.narrate(payload=_payload()) == "Your emergency fund covers 0.90 months."
    assert client.calls[0]["model"] == "gpt-4o-mini"


def test_sends_only_whitelisted_figure_keys() -> None:
    """`result_id` is an internal identifier and must not leave the system, per
    specs/ai-cfo.md's "only the minimum financial context required is sent".
    """
    client = RecordingClient()
    OpenAIInterpreter(client=client, model="gpt-4o-mini").narrate(payload=_payload())

    sent = json.loads(client.calls[0]["input"])
    assert sent["figures"] == [
        {
            "label": "Emergency fund after",
            "value": "0.90",
            "unit": "months",
            "source": "emergency_fund_engine",
        }
    ]
    assert "0192f0c1-0000-7000-8000-000000000001" not in client.calls[0]["input"]


def test_caps_the_reply_length() -> None:
    client = RecordingClient()
    OpenAIInterpreter(client=client, model="gpt-4o-mini", max_output_tokens=64).narrate(
        payload=_payload()
    )

    assert client.calls[0]["max_output_tokens"] == 64


@pytest.mark.parametrize(
    "error",
    [ConnectionError("provider unreachable"), TimeoutError("timed out"), RuntimeError("429")],
)
def test_a_provider_failure_degrades_to_no_narration(error: Exception) -> None:
    interpreter = OpenAIInterpreter(client=ExplodingClient(error), model="gpt-4o-mini")

    assert interpreter.narrate(payload=_payload()) is None


@pytest.mark.parametrize("output_text", [None, "", "   ", 42])
def test_an_unusable_reply_is_no_narration(output_text) -> None:
    interpreter = OpenAIInterpreter(
        client=RecordingClient(output_text=output_text), model="gpt-4o-mini"
    )

    assert interpreter.narrate(payload=_payload()) is None


def test_no_key_configured_yields_the_null_interpreter() -> None:
    """Requirement 12: the system stays usable with the model unavailable, and "not
    configured" is the same path as "unavailable".
    """
    from flask import Flask

    from app.llm.factory import build_interpreter
    from app.llm.interpreter import NullInterpreter

    app = Flask(__name__)
    app.config.update(OPENAI_API_KEY="", OPENAI_MODEL="gpt-4o-mini")

    with app.app_context():
        assert isinstance(build_interpreter(), NullInterpreter)
