"""AI CFO orchestration. See specs/ai-cfo.md and ADR-002.

The pipeline: classify intent, extract parameters, assemble context from result objects,
run the engine, narrate, return both. The figures are authoritative; the narration is
presentation, and the endpoint works with no provider at all.

Nothing in this module computes a financial figure either — every number it returns came
from `app/domain/`, and each carries the engine that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError
from app.domain.emergency_fund import emergency_fund_months
from app.domain.projection import FinancialPosition, project_forward
from app.llm.intent import (
    Capability,
    Intent,
    clarifying_question,
    classify,
    unsupported_explanation,
)
from app.llm.interpreter import Interpreter, NullInterpreter, build_narration_payload
from app.models.assistant import AssistantConversation, AssistantMessage
from app.repositories.assistant import AssistantRepository
from app.repositories.debt import DebtRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.health_assessment import HealthAssessmentRepository
from app.services.goal import GoalService
from app.services.position import PositionService

AFFORDABILITY_HORIZON_MONTHS = 12


@dataclass(frozen=True, slots=True)
class Figure:
    """One authoritative number, with the engine and stored result that produced it.

    `source` is the engine module, `result_id` the stored result where one exists — a
    computed-on-the-spot figure has no stored result and says so with None rather than
    inventing an identifier.
    """

    label: str
    value: str
    unit: str
    source: str
    result_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "result_id": self.result_id,
        }


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    supported: bool
    answer: str | None
    narration_available: bool
    figures: tuple[Figure, ...] = field(default_factory=tuple)
    based_on: dict = field(default_factory=dict)
    clarification: str | None = None
    capability: str = Capability.UNSUPPORTED.value
    conversation_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "supported": self.supported,
            "answer": self.answer,
            "narration_available": self.narration_available,
            "figures": [f.as_dict() for f in self.figures],
            "based_on": self.based_on,
            "clarification": self.clarification,
            "capability": self.capability,
            "conversation_id": self.conversation_id,
        }


class AssistantService:
    def __init__(self, session: DbSession, *, interpreter: Interpreter | None = None) -> None:
        self._session = session
        self._interpreter = interpreter or NullInterpreter()
        self._conversations = AssistantRepository(session)
        self._position = PositionService(session)
        self._forecasts = ForecastRepository(session)
        self._assessments = HealthAssessmentRepository(session)
        self._debts = DebtRepository(session)
        self._goals = GoalService(session)

    def ask(
        self,
        *,
        user_id: UUID,
        question: str,
        conversation_id: UUID | None = None,
        as_of: date | None = None,
    ) -> AssistantAnswer:
        """Run the whole pipeline for one question.

        A follow-up re-runs it from scratch: "Figures are never carried forward from
        conversation history, because the underlying position may have changed."
        """
        as_of = as_of or date.today()
        intent = classify(question, as_of=as_of)

        if not intent.is_supported:
            answer = AssistantAnswer(
                supported=False,
                answer=unsupported_explanation(intent),
                narration_available=False,
                capability=intent.capability.value,
            )
            return self._record(user_id=user_id, conversation_id=conversation_id, question=question, answer=answer)

        if intent.needs_clarification:
            answer = AssistantAnswer(
                supported=True,
                answer=None,
                narration_available=False,
                clarification=clarifying_question(intent),
                capability=intent.capability.value,
            )
            return self._record(user_id=user_id, conversation_id=conversation_id, question=question, answer=answer)

        figures, based_on = self._run_capability(
            user_id=user_id, intent=intent, as_of=as_of
        )

        narration = self._interpreter.narrate(
            payload=build_narration_payload(
                question=question, figures=[f.as_dict() for f in figures]
            )
        )
        answer = AssistantAnswer(
            supported=True,
            answer=narration,
            narration_available=narration is not None,
            figures=tuple(figures),
            based_on=based_on,
            capability=intent.capability.value,
        )
        return self._record(
            user_id=user_id, conversation_id=conversation_id, question=question, answer=answer
        )

    def _run_capability(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        handlers = {
            Capability.AFFORDABILITY_CHECK: self._affordability,
            Capability.SCENARIO_REQUEST: self._affordability,
            Capability.POSITION_QUERY: self._position_query,
            Capability.SPENDING_ANALYSIS: self._spending_analysis,
            Capability.DEBT_QUESTION: self._debt_question,
            Capability.GOAL_QUESTION: self._goal_question,
            Capability.FORECAST_QUESTION: self._forecast_question,
            Capability.FIGURE_EXPLANATION: self._position_query,
        }
        handler = handlers[intent.capability]
        return handler(user_id=user_id, intent=intent, as_of=as_of)

    def _base_context(self, *, user_id: UUID, as_of: date) -> dict:
        return {
            "period": f"{as_of.replace(day=1).isoformat()}/{as_of.isoformat()}",
            "assumptions": {},
        }

    def _affordability(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        """The worked example: "Can I afford a R15,000 holiday in December?"

        Runs the discretionary-expense path in memory rather than persisting a scenario:
        a question is not a saved scenario, and ADR-005's isolation requirement is met
        most simply by writing nothing at all. The engines are the same ones the stored
        scenario path uses.
        """
        amount = intent.parameters.amount or Decimal("0")
        position_value = self._position.compute_current(user_id=user_id, as_of=as_of)

        baseline = project_forward(
            position=position_value, horizon_months=AFFORDABILITY_HORIZON_MONTHS
        )
        after = project_forward(
            position=FinancialPosition(
                as_of=position_value.as_of,
                liquid_savings=position_value.liquid_savings - amount,
                total_debt=position_value.total_debt,
                net_worth=position_value.net_worth - amount,
                monthly_income=position_value.monthly_income,
                monthly_essential=position_value.monthly_essential,
                monthly_discretionary=position_value.monthly_discretionary,
            ),
            horizon_months=AFFORDABILITY_HORIZON_MONTHS,
        )

        savings_after = after[0].savings
        cover_after = (
            emergency_fund_months(
                liquid_savings=savings_after,
                monthly_essential_spending=position_value.monthly_essential,
            )
            if savings_after > 0 and position_value.monthly_essential > 0
            else Decimal("0.000000")
        )

        context = self._base_context(user_id=user_id, as_of=as_of)
        month = intent.parameters.month
        if month is None:
            context["assumptions"]["timing"] = (
                "Taken now; no month was given in the question."
            )
        else:
            context["assumptions"]["timing"] = (
                f"{intent.parameters.year:04d}-{month:02d}"
            )
        context["assumptions"]["horizon_months"] = str(AFFORDABILITY_HORIZON_MONTHS)

        return (
            [
                Figure("Amount", str(amount), "rand", "intent_extraction"),
                Figure(
                    "Liquid savings now",
                    str(position_value.liquid_savings),
                    "rand",
                    "position_service",
                ),
                Figure("Savings after", str(savings_after), "rand", "projection_engine"),
                Figure(
                    "Savings after, without the spend",
                    str(baseline[0].savings),
                    "rand",
                    "projection_engine",
                ),
                Figure(
                    "Emergency fund after",
                    str(cover_after),
                    "months",
                    "emergency_fund_engine",
                ),
                Figure(
                    "Monthly cash flow",
                    str(baseline[0].cash_flow),
                    "rand",
                    "projection_engine",
                ),
            ],
            context,
        )

    def _position_query(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        payload = self._position.dashboard_payload(user_id=user_id)
        assessment = self._assessments.latest_for_user(user_id=user_id)

        figures = [
            Figure("Net worth", payload["net_worth"] or "0", "rand", "net_worth_engine"),
            Figure(
                "Liquid savings", payload["liquid_savings"] or "0", "rand", "position_service"
            ),
            Figure("Total debt", payload["total_debt"] or "0", "rand", "position_service"),
            Figure(
                "Emergency fund",
                payload["emergency_fund_months"] or "0",
                "months",
                "emergency_fund_engine",
            ),
        ]
        if assessment is not None:
            figures.append(
                Figure(
                    "Financial health score",
                    str(assessment.score),
                    "points",
                    "financial_health_engine",
                    result_id=str(assessment.id),
                )
            )
        return figures, self._base_context(user_id=user_id, as_of=as_of)

    def _spending_analysis(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        position_value = self._position.compute_current(user_id=user_id, as_of=as_of)
        return (
            [
                Figure(
                    "Income this month",
                    str(position_value.monthly_income),
                    "rand",
                    "position_service",
                ),
                Figure(
                    "Essential spending",
                    str(position_value.monthly_essential),
                    "rand",
                    "position_service",
                ),
                Figure(
                    "Discretionary spending",
                    str(position_value.monthly_discretionary),
                    "rand",
                    "position_service",
                ),
                Figure(
                    "Remaining",
                    str(
                        position_value.monthly_income
                        - position_value.monthly_essential
                        - position_value.monthly_discretionary
                    ),
                    "rand",
                    "cash_flow_engine",
                ),
            ],
            self._base_context(user_id=user_id, as_of=as_of),
        )

    def _debt_question(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        debts = self._debts.list_for_user(user_id=user_id)
        total_balance = sum((d.current_balance for d in debts), Decimal("0"))
        total_payments = sum(
            (
                (d.instalment if d.instalment is not None else d.minimum_payment)
                for d in debts
            ),
            Decimal("0"),
        )
        figures = [
            Figure("Debts tracked", str(len(debts)), "count", "debt_repository"),
            Figure("Total debt balance", str(total_balance), "rand", "debt_repository"),
            Figure(
                "Monthly debt repayments", str(total_payments), "rand", "debt_repository"
            ),
        ]

        if debts:
            from app.services.debt import DebtService

            comparison = DebtService(self._session).compare_strategies(user_id=user_id)
            figures.extend(
                [
                    Figure(
                        "Months to debt free, avalanche",
                        str(comparison.avalanche.months_to_free),
                        "months",
                        "debt_payoff_engine",
                    ),
                    Figure(
                        "Total interest, avalanche",
                        str(comparison.avalanche.total_interest),
                        "rand",
                        "debt_payoff_engine",
                    ),
                ]
            )
        return figures, self._base_context(user_id=user_id, as_of=as_of)

    def _goal_question(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        goals = self._goals.list_for_user(user_id=user_id)
        figures: list[Figure] = [
            Figure("Goals tracked", str(len(goals)), "count", "goal_repository")
        ]
        for goal in goals[:3]:
            view = self._goals.progress(goal.id, user_id=user_id, as_of=as_of)
            figures.append(
                Figure(
                    f"{goal.name}: required monthly",
                    str(view.assessment.required_monthly_contribution),
                    "rand",
                    "goals_engine",
                    result_id=str(goal.id),
                )
            )
            figures.append(
                Figure(
                    f"{goal.name}: observed monthly",
                    str(view.assessment.observed_monthly_rate),
                    "rand",
                    "goals_engine",
                    result_id=str(goal.id),
                )
            )
        return figures, self._base_context(user_id=user_id, as_of=as_of)

    def _forecast_question(
        self, *, user_id: UUID, intent: Intent, as_of: date
    ) -> tuple[list[Figure], dict]:
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        context = self._base_context(user_id=user_id, as_of=as_of)
        if forecast is None:
            return (
                [Figure("Forecast available", "no", "boolean", "forecast_repository")],
                context,
            )

        periods = self._forecasts.periods_for(forecast.id)
        horizon = intent.parameters.horizon_months or len(periods)
        index = min(max(horizon, 1), len(periods)) - 1
        target = periods[index]
        context["assumptions"] = dict(forecast.assumptions or {})

        return (
            [
                Figure(
                    "Forecast generated",
                    forecast.generated_at.isoformat(),
                    "timestamp",
                    "forecast_service",
                    result_id=str(forecast.id),
                ),
                Figure(
                    "Is stale", "yes" if forecast.is_stale else "no", "boolean", "forecast_service"
                ),
                Figure(
                    f"Savings at {target.month}",
                    str(target.savings_balance),
                    "rand",
                    "forecast_engine",
                    result_id=str(forecast.id),
                ),
                Figure(
                    f"Net worth at {target.month}",
                    str(target.net_worth),
                    "rand",
                    "forecast_engine",
                    result_id=str(forecast.id),
                ),
                Figure(
                    f"Debt at {target.month}",
                    str(target.debt_balance),
                    "rand",
                    "forecast_engine",
                    result_id=str(forecast.id),
                ),
            ],
            context,
        )

    def _record(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        question: str,
        answer: AssistantAnswer,
    ) -> AssistantAnswer:
        """Persist the exchange.

        The narration is stored on a conversation message, which is a transcript field —
        never a financial column. No figure stored here is ever read back as an input to
        a calculation; a follow-up re-runs the engines instead.
        """
        conversation = None
        if conversation_id is not None:
            conversation = self._conversations.get_for_user(conversation_id, user_id=user_id)
            if conversation is None:
                raise NotFoundError(
                    "No conversation with that identifier exists for this user."
                )
        if conversation is None:
            conversation = self._conversations.add_conversation(
                AssistantConversation(
                    user_id=user_id,
                    started_at=datetime.now(UTC),
                    title=question[:120],
                )
            )

        self._conversations.add_message(
            AssistantMessage(
                conversation_id=conversation.id,
                user_id=user_id,
                asked_at=datetime.now(UTC),
                question=question,
                answer=answer.answer,
                capability=answer.capability,
                supported=answer.supported,
                figures=[f.as_dict() for f in answer.figures],
            )
        )
        self._session.commit()

        return AssistantAnswer(
            supported=answer.supported,
            answer=answer.answer,
            narration_available=answer.narration_available,
            figures=answer.figures,
            based_on=answer.based_on,
            clarification=answer.clarification,
            capability=answer.capability,
            conversation_id=str(conversation.id),
        )

    def list_conversations(self, *, user_id: UUID) -> list[AssistantConversation]:
        return self._conversations.list_for_user(user_id=user_id)

    def conversation(self, conversation_id: UUID, *, user_id: UUID) -> tuple:
        conversation = self._conversations.get_for_user(conversation_id, user_id=user_id)
        if conversation is None:
            raise NotFoundError("No conversation with that identifier exists for this user.")
        return conversation, self._conversations.messages_for(conversation.id, user_id=user_id)
