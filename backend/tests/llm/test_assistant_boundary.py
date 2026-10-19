"""ADR-002's testable invariant: "A test asserts no model output is written to a
financial column" (specs/ai-cfo.md acceptance criteria).

This is a structural test rather than a behavioural one. It asserts over the mapped
schema, so it fails when a future migration adds a model-writable column to a financial
table — which is the moment the invariant would break, not the moment someone happens to
exercise the path.
"""

from __future__ import annotations

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.base import Base

# Tables holding real or derived financial state. Model output may not reach any of them.
# Written schema-qualified, as `Table.fullname` reports them: the `ledger` and `analytics`
# schemas are the boundary this test is about, so naming a table without its schema would
# let a second `transactions` in another schema pass unnoticed.
FINANCIAL_TABLES = {
    "ledger.accounts",
    "ledger.transactions",
    "ledger.import_batches",
    "ledger.staged_transactions",
    "obligations.debts",
    "obligations.goals",
    "obligations.goal_contributions",
    "analytics.position_snapshots",
    "analytics.forecasts",
    "analytics.forecast_periods",
    "analytics.forecast_accuracy",
    "analytics.health_assessments",
    "analytics.risk_flags",
    "analytics.recommendations",
    "analytics.scenarios",
    "analytics.scenario_assumptions",
    "analytics.scenario_results",
}

# The only tables model-generated prose is permitted to land in. They are the whole of the
# `assistant` schema, which is why that schema exists separately from `analytics`.
NARRATION_TABLES = {"assistant.conversations", "assistant.messages"}


def test_model_output_is_confined_to_the_assistant_transcript_tables() -> None:
    assert AssistantMessage.__table__.fullname in NARRATION_TABLES
    assert AssistantConversation.__table__.fullname in NARRATION_TABLES
    assert NARRATION_TABLES.isdisjoint(FINANCIAL_TABLES)



def test_the_assistant_service_writes_only_to_narration_tables() -> None:
    """The service's own writes, read off its source rather than guessed at.

    AssistantService constructs exactly two model types. If a future change has it
    constructing a financial model, this fails.
    """
    import ast
    import inspect

    import app.services.assistant as assistant_module

    tree = ast.parse(inspect.getsource(assistant_module))
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    financial_models = {
        "Account",
        "Transaction",
        "Debt",
        "Goal",
        "GoalContribution",
        "PositionSnapshot",
        "Forecast",
        "ForecastPeriod",
        "ForecastAccuracy",
        "HealthAssessment",
        "RiskFlag",
        "Recommendation",
        "Scenario",
        "ScenarioResult",
    }
    assert constructed.isdisjoint(financial_models), (
        "AssistantService constructs a financial model: model output must never reach "
        "a financial table (ADR-002)"
    )
    assert {"AssistantConversation", "AssistantMessage"} <= constructed


def test_every_financial_table_named_here_actually_exists() -> None:
    """Guards the guard: a renamed table must not silently drop out of the check."""
    mapped = set(Base.metadata.tables)
    missing = (FINANCIAL_TABLES | NARRATION_TABLES) - mapped
    assert not missing, f"This test names tables that no longer exist: {missing}"


def test_no_financial_table_has_a_narration_column() -> None:
    """Model prose is stored as `answer`; no financial table may carry such a column."""
    narration_column_names = {"answer", "narration", "explanation_text", "llm_response"}

    for table_name in FINANCIAL_TABLES:
        table = Base.metadata.tables[table_name]
        offending = narration_column_names & set(table.columns.keys())
        assert not offending, f"{table_name} carries narration column(s): {offending}"
