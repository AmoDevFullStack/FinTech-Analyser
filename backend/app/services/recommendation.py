"""Recommendation orchestration. See specs/recommendations.md.

Assembles each rule's inputs from stored results, renders the figures into a sentence, and
applies the lifecycle: rank by benefit, cap at five active, and keep a dismissed rule
suppressed for 60 days unless its benefit has materially increased.

Copy discipline, from the spec: "Never framed as advice. 'Redirecting R500 here saves
R14,200 in interest' is a calculation; 'you should redirect R500' is advice." Every
sentence composed below states what a figure would be, never what the user ought to do.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError
from app.domain.debt_payoff import DebtInput
from app.domain.recommendations import (
    MAX_ACTIVE,
    GoalShortfall,
    Recommendation as RuleResult,
    Rule,
    SubscriptionCandidate,
    build_emergency_cover,
    goal_contribution_shortfall,
    rank_and_cap,
    redirect_to_highest_rate_debt,
    refinance_candidate,
    subscription_audit,
    surplus_not_allocated,
    utilisation_reduction,
)
from app.models.account import AccountType
from app.models.category import CategoryKind
from app.models.recommendation import Recommendation, RecommendationStatus
from app.repositories.account import AccountRepository
from app.repositories.debt import DebtRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.recommendation import RecommendationRepository
from app.services.goal import GoalService
from app.services.position import PositionService
from app.services.recurrence import RecurrenceService

DISMISSAL_SUPPRESSION_DAYS = 60
# What counts as a "material" increase in benefit, enough to override a dismissal: a
# quarter more than the figure the user dismissed. A rule whose benefit creeps up by a
# rand must not reappear, or dismissal means nothing.
MATERIAL_INCREASE = Decimal("1.25")
SURPLUS_HISTORY_MONTHS = 6


def _rand(amount: Decimal) -> str:
    whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"R{whole:,}"


def _percent(ratio: str) -> str:
    return f"{(Decimal(ratio) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def compose_explanation(result: RuleResult) -> str:
    """Render a rule result as a calculation, never as an instruction."""
    details = result.details

    if result.rule is Rule.REDIRECT_TO_HIGHEST_RATE_DEBT:
        return (
            f"Directing the {_rand(Decimal(details['monthly_surplus']))} monthly surplus at the "
            f"{_percent(details['target_annual_rate'])} debt reduces total interest by "
            f"{_rand(result.benefit_amount)} and clears the debt set "
            f"{details['months_saved']} months sooner."
        )

    if result.rule is Rule.BUILD_EMERGENCY_COVER:
        return (
            f"Cover is {Decimal(details['current_cover_months']).quantize(Decimal('0.1'))} months. "
            f"Reaching {details['target_months']} months means "
            f"{_rand(Decimal(details['required_balance']))} held, "
            f"{_rand(result.benefit_amount)} more than now — "
            f"{_rand(Decimal(details['monthly_amount']))} a month over "
            f"{details['build_months']} months."
        )

    if result.rule is Rule.SUBSCRIPTION_AUDIT:
        return (
            f"{details['series']} costs {_rand(Decimal(details['monthly_equivalent']))} a month, "
            f"{_rand(result.benefit_amount)} a year, and is "
            f"{_percent(details['share_of_discretionary'])} of discretionary spending. "
            f"Last charged {details['last_charged_on']}."
        )

    if result.rule is Rule.UTILISATION_REDUCTION:
        return (
            f"Revolving utilisation is {_percent(details['utilisation'])}. Repaying "
            f"{_rand(result.benefit_amount)} brings it to {_percent(details['target'])}."
        )

    if result.rule is Rule.GOAL_CONTRIBUTION_SHORTFALL:
        slippage = details.get("slippage_months")
        tail = f" At the observed rate the target date moves out by {slippage} months." if slippage else ""
        return (
            f"{details['goal_name']} needs "
            f"{_rand(Decimal(details['required_monthly']))} a month and is receiving "
            f"{_rand(Decimal(details['observed_monthly']))}, a gap of "
            f"{_rand(result.benefit_amount)}.{tail}"
        )

    if result.rule is Rule.REFINANCE_CANDIDATE:
        return (
            f"One debt of {_rand(Decimal(details['balance']))} carries "
            f"{_percent(details['debt_annual_rate'])} against a weighted average of "
            f"{_percent(details['weighted_average_rate'])} across all debts. The difference is "
            f"{_rand(result.benefit_amount)} of interest in the first year."
        )

    if result.rule is Rule.SURPLUS_NOT_ALLOCATED:
        return (
            f"{_rand(Decimal(details['monthly_amount']))} a month has been left unallocated for "
            f"{details['months_observed']} months. Saved, that is "
            f"{_rand(Decimal(details['annual_contributions']))} in a year plus "
            f"{_rand(Decimal(details['interest_if_saved']))} of interest at "
            f"{_percent(details['assumed_annual_rate'])}."
        )

    raise AssertionError(f"No copy defined for rule {result.rule}")


def _months_ago(as_of: date, months: int) -> date:
    total = as_of.month - 1 - months
    year = as_of.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year, 12, 31)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


class RecommendationService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._recommendations = RecommendationRepository(session)
        self._accounts = AccountRepository(session)
        self._debts = DebtRepository(session)
        self._forecasts = ForecastRepository(session)
        self._position = PositionService(session)
        self._recurrence = RecurrenceService(session)
        self._goals = GoalService(session)

    def evaluate(self, *, user_id: UUID, as_of: date | None = None) -> list[Recommendation]:
        """Run every rule, rank by benefit, cap at five, and reconcile with what exists.

        Called by the worker after forecast regeneration, per the spec.
        """
        as_of = as_of or date.today()
        results = rank_and_cap(self._run_rules(user_id=user_id, as_of=as_of), maximum=MAX_ACTIVE)

        for result in results:
            self._reconcile(user_id=user_id, result=result, as_of=as_of)
        self._session.commit()

        return self._recommendations.list_for_user(
            user_id=user_id, status=RecommendationStatus.ACTIVE
        )

    def _run_rules(self, *, user_id: UUID, as_of: date) -> list[RuleResult]:
        position = self._position.compute_current(user_id=user_id, as_of=as_of)
        accounts = self._accounts.list_for_user(user_id=user_id)
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        reference = (
            f"forecast:{forecast.id}" if forecast else f"position:{as_of.isoformat()}"
        )

        debts = [
            DebtInput(
                id=str(d.id),
                current_balance=d.current_balance,
                annual_rate=d.annual_rate,
                minimum_payment=(
                    d.instalment if d.instalment is not None else d.minimum_payment
                ),
            )
            for d in self._debts.list_for_user(user_id=user_id)
            if d.current_balance > 0
        ]
        surplus = (
            position.monthly_income
            - position.monthly_essential
            - position.monthly_discretionary
            - sum((d.minimum_payment for d in debts), Decimal("0"))
        )

        credit_accounts = [a for a in accounts if a.account_type is AccountType.CREDIT_CARD]
        revolving_balance = sum(
            (max(Decimal("0"), -a.current_balance) for a in credit_accounts), Decimal("0")
        )
        credit_limit = sum(
            (a.credit_limit or Decimal("0") for a in credit_accounts), Decimal("0")
        )

        candidates = [
            SubscriptionCandidate(
                key=view.series.key,
                monthly_equivalent=view.series.monthly_equivalent,
                annual_cost=view.series.annual_cost,
                last_charged_on=view.series.last_seen.isoformat(),
            )
            for view in self._recurrence.detect(user_id=user_id)
            if view.category_kind is CategoryKind.DISCRETIONARY
            and view.series.median_amount < 0
        ]

        results = [
            redirect_to_highest_rate_debt(
                debts=debts, monthly_surplus=surplus, computation_reference=reference
            ),
            build_emergency_cover(
                liquid_savings=position.liquid_savings,
                monthly_essential=position.monthly_essential,
                computation_reference=reference,
            ),
            subscription_audit(
                candidates=candidates,
                monthly_discretionary=position.monthly_discretionary,
                computation_reference=reference,
            ),
            utilisation_reduction(
                revolving_balance=revolving_balance,
                credit_limit=credit_limit,
                computation_reference=reference,
            ),
            goal_contribution_shortfall(
                shortfalls=self._goal_shortfalls(user_id=user_id, as_of=as_of),
                computation_reference=reference,
            ),
            refinance_candidate(debts=debts, computation_reference=reference),
            surplus_not_allocated(
                monthly_surpluses=self._monthly_surpluses(
                    user_id=user_id, as_of=as_of, accounts=accounts
                ),
                computation_reference=reference,
            ),
        ]
        return [result for result in results if result is not None]

    def _goal_shortfalls(self, *, user_id: UUID, as_of: date) -> list[GoalShortfall]:
        shortfalls = []
        for goal in self._goals.list_for_user(user_id=user_id):
            view = self._goals.progress(goal.id, user_id=user_id, as_of=as_of)
            shortfalls.append(
                GoalShortfall(
                    goal_id=str(goal.id),
                    name=goal.name,
                    required_monthly=view.assessment.required_monthly_contribution,
                    observed_monthly=view.assessment.observed_monthly_rate,
                    slippage_months=view.assessment.date_slippage_months,
                )
            )
        return shortfalls

    def _monthly_surpluses(self, *, user_id: UUID, as_of: date, accounts) -> list[Decimal]:
        """Income less all spending, per complete month, oldest first."""
        surpluses = []
        for offset in range(SURPLUS_HISTORY_MONTHS, 0, -1):
            start = _months_ago(as_of, offset)
            sums = self._position.category_kind_sums(
                user_id=user_id, accounts=accounts, since=start, until=_month_end(start)
            )
            if sums[CategoryKind.INCOME] == 0:
                continue
            surpluses.append(
                sums[CategoryKind.INCOME]
                - sums[CategoryKind.ESSENTIAL]
                - sums[CategoryKind.DISCRETIONARY]
                - sums[CategoryKind.DEBT]
                - sums[CategoryKind.SAVING]
            )
        return surpluses

    def _reconcile(self, *, user_id: UUID, result: RuleResult, as_of: date) -> None:
        """Update, suppress, or create — the lifecycle rules from the spec."""
        existing = self._recommendations.latest_of_rule(
            user_id=user_id, rule_id=result.rule.value
        )
        explanation = compose_explanation(result)

        if existing is not None and existing.status is RecommendationStatus.DISMISSED:
            dismissed_at = existing.dismissed_at
            still_suppressed = (
                dismissed_at is not None
                and datetime.now(UTC) - dismissed_at
                < timedelta(days=DISMISSAL_SUPPRESSION_DAYS)
            )
            materially_better = result.benefit_amount > existing.benefit_amount * MATERIAL_INCREASE
            if still_suppressed and not materially_better:
                return

        if existing is not None and existing.status is RecommendationStatus.ACTIVE:
            existing.benefit_amount = result.benefit_amount
            existing.benefit_kind = result.benefit_kind
            existing.explanation = explanation
            existing.computation_reference = result.computation_reference
            existing.details = result.details
            existing.generated_on = as_of
            return

        self._recommendations.add(
            Recommendation(
                user_id=user_id,
                rule_id=result.rule.value,
                status=RecommendationStatus.ACTIVE,
                benefit_amount=result.benefit_amount,
                benefit_kind=result.benefit_kind,
                explanation=explanation,
                computation_reference=result.computation_reference,
                details=result.details,
                generated_on=as_of,
            )
        )

    def list_recommendations(
        self, *, user_id: UUID, status: RecommendationStatus | None
    ) -> list[Recommendation]:
        return self._recommendations.list_for_user(user_id=user_id, status=status)

    def dismiss(self, recommendation_id: UUID, *, user_id: UUID) -> Recommendation:
        recommendation = self._get(recommendation_id, user_id=user_id)
        recommendation.status = RecommendationStatus.DISMISSED
        recommendation.dismissed_at = datetime.now(UTC)
        self._session.commit()
        return recommendation

    def mark_acted_on(self, recommendation_id: UUID, *, user_id: UUID) -> Recommendation:
        recommendation = self._get(recommendation_id, user_id=user_id)
        recommendation.status = RecommendationStatus.ACTED_ON
        self._session.commit()
        return recommendation

    def _get(self, recommendation_id: UUID, *, user_id: UUID) -> Recommendation:
        recommendation = self._recommendations.get_for_user(
            recommendation_id, user_id=user_id
        )
        if recommendation is None:
            raise NotFoundError(
                "No recommendation with that identifier exists for this user."
            )
        return recommendation
