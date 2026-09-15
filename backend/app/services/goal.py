"""Goal orchestration. See specs/goals.md.

All arithmetic is in app/domain/goals.py. This service's job is to establish two figures
the engine cannot know — how much a goal has actually accumulated, and how fast it is
actually accumulating — and it must derive both from evidence, never from the user's
stated plan. That distinction is the whole feature: "The gap between the two is the most
useful thing this feature produces."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError, ValidationError
from app.domain.goals import (
    GoalAssessment,
    GoalRequirement,
    FundingPlan,
    allocate_across_goals,
    assess_goal,
    months_between,
)
from app.models.goal import Goal, GoalContribution
from app.repositories.account import AccountRepository
from app.repositories.goal import GoalRepository
from app.repositories.transaction import TransactionRepository
from app.services.position import PositionService

CENTS = Decimal("0.01")
OBSERVED_RATE_MONTHS = 3  # specs/goals.md: "the actual observed contribution rate over
# the last three months, not the planned rate."


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _months_ago(as_of: date, months: int) -> date:
    total = as_of.month - 1 - months
    year = as_of.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


@dataclass(frozen=True, slots=True)
class CreateGoalInput:
    name: str
    target_amount: Decimal
    target_date: date
    priority: int = 1
    account_id: UUID | None = None
    opening_amount: Decimal = Decimal("0")
    planned_monthly_contribution: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UpdateGoalInput:
    name: str | None = None
    target_amount: Decimal | None = None
    target_date: date | None = None
    priority: int | None = None
    account_id: UUID | None = None
    planned_monthly_contribution: Decimal | None = None


@dataclass(frozen=True, slots=True)
class GoalProgressView:
    goal: Goal
    assessment: GoalAssessment
    progress_source: str  # "linked_account" | "contributions" | "none"
    annual_rate: Decimal


class GoalService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._goals = GoalRepository(session)
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._position = PositionService(session)

    def create(self, *, user_id: UUID, data: CreateGoalInput) -> Goal:
        if data.target_amount <= 0:
            raise ValidationError("target_amount must be positive.")
        if data.priority < 1:
            raise ValidationError("priority must be 1 or greater.")
        if data.account_id is not None and self._accounts.get_for_user(
            data.account_id, user_id=user_id
        ) is None:
            raise ValidationError("No account with that identifier exists for this user.")

        goal = Goal(
            user_id=user_id,
            account_id=data.account_id,
            name=data.name,
            target_amount=data.target_amount,
            current_amount=data.opening_amount,
            target_date=data.target_date,
            priority=data.priority,
            planned_monthly_contribution=data.planned_monthly_contribution,
        )
        self._goals.add(goal)
        self._session.commit()
        return goal

    def list_for_user(self, *, user_id: UUID) -> list[Goal]:
        return self._goals.list_for_user(user_id=user_id)

    def get(self, goal_id: UUID, *, user_id: UUID) -> Goal:
        goal = self._goals.get_for_user(goal_id, user_id=user_id)
        if goal is None:
            raise NotFoundError("No goal with that identifier exists for this user.")
        return goal

    def update(self, goal_id: UUID, *, user_id: UUID, data: UpdateGoalInput) -> Goal:
        goal = self.get(goal_id, user_id=user_id)

        if data.name is not None:
            goal.name = data.name
        if data.target_amount is not None:
            if data.target_amount <= 0:
                raise ValidationError("target_amount must be positive.")
            goal.target_amount = data.target_amount
        if data.target_date is not None:
            goal.target_date = data.target_date
        if data.priority is not None:
            if data.priority < 1:
                raise ValidationError("priority must be 1 or greater.")
            goal.priority = data.priority
        if data.account_id is not None:
            if self._accounts.get_for_user(data.account_id, user_id=user_id) is None:
                raise ValidationError("No account with that identifier exists for this user.")
            goal.account_id = data.account_id
        if data.planned_monthly_contribution is not None:
            goal.planned_monthly_contribution = data.planned_monthly_contribution

        self._session.commit()
        return goal

    def soft_delete(self, goal_id: UUID, *, user_id: UUID) -> None:
        goal = self.get(goal_id, user_id=user_id)
        goal.deleted_at = datetime.now(UTC)
        self._session.commit()

    def record_contribution(
        self,
        goal_id: UUID,
        *,
        user_id: UUID,
        amount: Decimal,
        occurred_on: date,
        note: str | None = None,
    ) -> GoalContribution:
        goal = self.get(goal_id, user_id=user_id)
        if amount <= 0:
            raise ValidationError("A contribution amount must be positive.")

        contribution = GoalContribution(
            goal_id=goal.id,
            user_id=user_id,
            amount=amount,
            occurred_on=occurred_on,
            note=note,
        )
        self._goals.add_contribution(contribution)
        self._session.commit()
        return contribution

    def _evidenced_progress(
        self, goal: Goal, *, user_id: UUID, as_of: date
    ) -> tuple[Decimal, Decimal, str, Decimal]:
        """Return (current_amount, observed_monthly_rate, source, annual_rate).

        Linked account: the account's balance is the goal's money, and the observed rate
        is its net movement over the trailing three months divided by three. Transfer
        legs are deliberately *included* here, unlike everywhere else in the system — a
        transfer from the cheque account into the savings account is precisely how a user
        funds a savings goal, and excluding it would report a diligent saver's rate as
        zero.

        No linked account: progress is the stated opening amount plus recorded
        contributions, and the rate is the last three months of those contributions.

        Neither: the opening amount and a rate of zero — "A goal with neither shows no
        progress rather than an optimistic estimate."
        """
        window_start = _months_ago(as_of, OBSERVED_RATE_MONTHS)

        if goal.account_id is not None:
            account = self._accounts.get_for_user(goal.account_id, user_id=user_id)
            if account is not None:
                movements = self._transactions.by_account(
                    account.id, user_id=user_id, since=window_start, until=as_of, limit=10_000
                )
                net = sum((t.amount for t in movements), Decimal("0"))
                rate = _quantise(max(Decimal("0"), net) / Decimal(OBSERVED_RATE_MONTHS))
                return (
                    account.current_balance,
                    rate,
                    "linked_account",
                    account.interest_rate or Decimal("0"),
                )

        contributions = self._goals.contributions_for(goal.id, user_id=user_id)
        total = sum((c.amount for c in contributions), Decimal("0"))
        recent = sum(
            (c.amount for c in contributions if c.occurred_on >= window_start), Decimal("0")
        )
        rate = _quantise(recent / Decimal(OBSERVED_RATE_MONTHS))
        source = "contributions" if contributions else "none"
        return goal.current_amount + total, rate, source, Decimal("0")

    def progress(
        self, goal_id: UUID, *, user_id: UUID, as_of: date | None = None
    ) -> GoalProgressView:
        as_of = as_of or date.today()
        goal = self.get(goal_id, user_id=user_id)
        return self._progress_for(goal, user_id=user_id, as_of=as_of)

    def _progress_for(self, goal: Goal, *, user_id: UUID, as_of: date) -> GoalProgressView:
        current, observed_rate, source, annual_rate = self._evidenced_progress(
            goal, user_id=user_id, as_of=as_of
        )
        available = self._available_cash_flow(user_id=user_id, as_of=as_of)

        assessment = assess_goal(
            target_amount=goal.target_amount,
            current_amount=current,
            target_date=goal.target_date,
            as_of=as_of,
            observed_monthly_rate=observed_rate,
            available_cash_flow=available,
            annual_rate=annual_rate,
        )
        return GoalProgressView(
            goal=goal, assessment=assessment, progress_source=source, annual_rate=annual_rate
        )

    def _available_cash_flow(self, *, user_id: UUID, as_of: date) -> Decimal:
        position = self._position.compute_current(user_id=user_id, as_of=as_of)
        return (
            position.monthly_income
            - position.monthly_essential
            - position.monthly_discretionary
        )

    def funding_plan(self, *, user_id: UUID, as_of: date | None = None) -> FundingPlan:
        """Competition between goals: one pool of cash, funded in priority order.

        "Goals are not modelled in isolation because they are not funded in isolation."
        """
        as_of = as_of or date.today()
        goals = self.list_for_user(user_id=user_id)
        available = self._available_cash_flow(user_id=user_id, as_of=as_of)

        requirements = []
        for goal in goals:
            view = self._progress_for(goal, user_id=user_id, as_of=as_of)
            current, _, _, annual_rate = self._evidenced_progress(
                goal, user_id=user_id, as_of=as_of
            )
            requirements.append(
                GoalRequirement(
                    key=str(goal.id),
                    priority=goal.priority,
                    required_monthly=view.assessment.required_monthly_contribution,
                    target_amount=goal.target_amount,
                    current_amount=current,
                    months_remaining=max(1, months_between(start=as_of, end=goal.target_date)),
                    annual_rate=annual_rate,
                )
            )

        return allocate_across_goals(goals=requirements, available_cash_flow=available)
