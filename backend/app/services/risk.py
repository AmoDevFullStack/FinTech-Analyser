"""Risk flag orchestration. See specs/risk-detection.md.

Three responsibilities the detectors in app/domain/risk.py deliberately do not have:
assembling their inputs from stored results, rendering each finding into the spec's copy
style, and the lifecycle rules — deduplicate an active flag of the same type rather than
duplicating it, and keep a dismissed flag suppressed for 30 days unless its severity
increases.

Copy conventions (specs/risk-detection.md): state the figure and the date; never
characterise the person. Every sentence composed here is about money and dates, never
about behaviour — "You have been overspending on dining out" is exactly what this must
not produce.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import NotFoundError
from app.domain.recurrence import next_occurrence_of_day
from app.domain.risk import (
    CategorySpend,
    Obligation,
    ProjectedPeriod,
    RiskFinding,
    RiskType,
    Severity,
    detect_anomalous_spending,
    detect_cash_flow_shortfall,
    detect_credit_utilisation,
    detect_debt_burden,
    detect_emergency_reserve_depletion,
    detect_obligation_coverage_gap,
    severity_rank,
)
from app.models.account import AccountType
from app.models.risk_flag import RiskFlag, RiskStatus
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.debt import DebtRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.health_assessment import HealthAssessmentRepository
from app.repositories.risk_flag import RiskFlagRepository
from app.repositories.transaction import TransactionRepository
from app.services.position import PositionService
from app.services.recurrence import RecurrenceService

DISMISSAL_SUPPRESSION_DAYS = 30
BASELINE_MONTHS = 6
OBLIGATION_WINDOW_DAYS = 60

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _rand(amount: Decimal) -> str:
    """Render a rand figure for copy: thousands-separated, to the nearest rand.

    The exact `Decimal` is preserved on the flag's `quantified_amount`; this is the
    display string only, and it rounds to whole rand because that is how the spec's own
    example copy reads ("R6,843", "R4,210"). Presentation rounding never feeds a
    calculation.
    """
    whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"R{whole:,}"


def _day_month(value: date) -> str:
    return f"{value.day} {_MONTH_NAMES[value.month - 1]}"


def _month_year(value: date) -> str:
    return f"{_MONTH_NAMES[value.month - 1]} {value.year}"


def _percent(ratio: str) -> str:
    return f"{(Decimal(ratio) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def compose_explanation(finding: RiskFinding) -> str:
    """Render a finding into the spec's copy style: figures and dates, no characterisation."""
    details = finding.details
    amount = _rand(finding.quantified_amount)

    if finding.risk_type is RiskType.CASH_FLOW_SHORTFALL:
        month = _month_year(finding.projected_date) if finding.projected_date else "the horizon"
        return (
            f"Projected outflows in {month} are {amount} more than projected income plus "
            f"available funds. Projected income is {_rand(Decimal(details['projected_inflows']))}, "
            f"outflows {_rand(Decimal(details['projected_outflows']))}, and available funds "
            f"{_rand(Decimal(details['available_funds']))}."
        )

    if finding.risk_type is RiskType.OBLIGATION_COVERAGE_GAP:
        due = _day_month(finding.projected_date) if finding.projected_date else "its due date"
        return (
            f"Your {details['obligation']} of "
            f"{_rand(Decimal(details['obligation_amount']))} is due on {due}. Projected "
            f"available funds that month are {_rand(Decimal(details['available_funds']))}, "
            f"leaving {amount} short."
        )

    if finding.risk_type is RiskType.EMERGENCY_RESERVE_DEPLETION:
        month = _month_year(finding.projected_date) if finding.projected_date else "the horizon"
        cover = Decimal(details["projected_cover_months"]).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        return (
            f"Projected emergency cover falls to {cover} months in {month}, which is "
            f"{amount} below one month of essential spending."
        )

    if finding.risk_type is RiskType.DEBT_BURDEN_THRESHOLD:
        return (
            f"Debt repayments of {_rand(Decimal(details['monthly_debt_service']))} a month are "
            f"{_percent(details['debt_to_income'])} of income, {amount} above the "
            f"{_percent(details['threshold'])} threshold."
        )

    if finding.risk_type is RiskType.ANOMALOUS_SPENDING:
        return (
            f"{details['category']} is {_rand(Decimal(details['current_monthly']))} this month "
            f"against a {_rand(Decimal(details['baseline_monthly']))} trailing baseline, "
            f"{amount} higher."
        )

    if finding.risk_type is RiskType.CREDIT_UTILISATION:
        return (
            f"Revolving balance is {_rand(Decimal(details['revolving_balance']))} against a "
            f"{_rand(Decimal(details['credit_limit']))} limit, a utilisation of "
            f"{_percent(details['utilisation'])}. Repaying {amount} brings it to "
            f"{_percent(details['threshold'])}."
        )

    raise AssertionError(f"No copy defined for risk type {finding.risk_type}")


def _months_ago(as_of: date, months: int) -> date:
    total = as_of.month - 1 - months
    year = as_of.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


class RiskService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._flags = RiskFlagRepository(session)
        self._forecasts = ForecastRepository(session)
        self._accounts = AccountRepository(session)
        self._debts = DebtRepository(session)
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)
        self._assessments = HealthAssessmentRepository(session)
        self._position = PositionService(session)
        self._recurrence = RecurrenceService(session)

    def evaluate(self, *, user_id: UUID, as_of: date | None = None) -> list[RiskFlag]:
        """Run all six detectors and reconcile the findings with existing flags.

        Called by the worker after each forecast regeneration and each import, per the
        spec. Returns the flags that are active after reconciliation.
        """
        as_of = as_of or date.today()
        findings = self._detect(user_id=user_id, as_of=as_of)

        for finding in findings:
            self._reconcile(user_id=user_id, finding=finding, as_of=as_of)
        self._session.commit()

        return self._flags.list_for_user(user_id=user_id, status=RiskStatus.ACTIVE)

    def _detect(self, *, user_id: UUID, as_of: date) -> list[RiskFinding]:
        position = self._position.compute_current(user_id=user_id, as_of=as_of)
        accounts = self._accounts.list_for_user(user_id=user_id)
        forecast = self._forecasts.latest_for_user(user_id=user_id)
        periods = self._projected_periods(forecast)
        forecast_id = str(forecast.id) if forecast else "none"

        assessment = self._assessments.latest_for_user(user_id=user_id)
        assessment_reference = (
            f"health_assessment:{assessment.id}" if assessment else f"position:{as_of.isoformat()}"
        )
        position_reference = f"position:{as_of.isoformat()}"

        debts = self._debts.list_for_user(user_id=user_id)
        monthly_debt_service = sum((d.minimum_payment for d in debts), Decimal("0"))

        credit_accounts = [a for a in accounts if a.account_type is AccountType.CREDIT_CARD]
        revolving_balance = sum(
            (max(Decimal("0"), -a.current_balance) for a in credit_accounts), Decimal("0")
        )
        credit_limit = sum(
            (a.credit_limit or Decimal("0") for a in credit_accounts), Decimal("0")
        )

        candidates = [
            detect_cash_flow_shortfall(
                periods=periods,
                monthly_income=position.monthly_income,
                forecast_id=forecast_id,
            )
            if periods
            else None,
            detect_obligation_coverage_gap(
                obligations=self._obligations(user_id=user_id, as_of=as_of, debts=debts),
                periods=periods,
                monthly_income=position.monthly_income,
                forecast_id=forecast_id,
            )
            if periods
            else None,
            detect_emergency_reserve_depletion(
                periods=periods,
                monthly_essential=position.monthly_essential,
                forecast_id=forecast_id,
            )
            if periods
            else None,
            detect_debt_burden(
                monthly_debt_service=monthly_debt_service,
                monthly_income=position.monthly_income,
                assessment_reference=assessment_reference,
                as_of=as_of,
            ),
            detect_anomalous_spending(
                categories=self._category_spend(user_id=user_id, as_of=as_of),
                monthly_income=position.monthly_income,
                as_of=as_of,
                position_reference=position_reference,
            ),
            detect_credit_utilisation(
                revolving_balance=revolving_balance,
                credit_limit=credit_limit,
                as_of=as_of,
                position_reference=position_reference,
            ),
        ]
        return [finding for finding in candidates if finding is not None]

    def _projected_periods(self, forecast) -> list[ProjectedPeriod]:
        if forecast is None:
            return []
        return [
            ProjectedPeriod(
                month=row.month,
                starts_on=date(int(row.month[:4]), int(row.month[5:7]), 1),
                inflows=row.projected_income,
                outflows=row.projected_expenses,
                liquid_funds=row.savings_balance,
                emergency_fund_months=row.emergency_fund_months,
            )
            for row in self._forecasts.periods_for(forecast.id)
        ]

    def _obligations(self, *, user_id: UUID, as_of: date, debts) -> list[Obligation]:
        """Upcoming obligations: each debt's contractual payment, plus detected recurring
        outflows.

        A `Debt` carries no due-day column (docs/database.md §3), so its due day is taken
        from `started_on` — a loan that started on the 25th is collected on the 25th. That
        is a derivation, not a fact, and it is stated here rather than hidden.
        """
        obligations: list[Obligation] = []
        for debt in debts:
            payment = debt.instalment if debt.instalment is not None else debt.minimum_payment
            due = next_occurrence_of_day(as_of=as_of, day=debt.started_on.day)
            obligations.append(
                Obligation(
                    label=f"{debt.debt_type.value.replace('_', ' ')} instalment",
                    amount=payment,
                    due_on=due,
                )
            )

        for row in self._recurrence.upcoming(
            user_id=user_id, from_date=as_of, days_ahead=OBLIGATION_WINDOW_DAYS
        ):
            obligations.append(
                Obligation(
                    label=row["label"],
                    amount=Decimal(row["amount"]),
                    due_on=date.fromisoformat(row["due_on"]),
                )
            )
        return obligations

    def _category_spend(self, *, user_id: UUID, as_of: date) -> list[CategorySpend]:
        """Current-month spend per category against a trailing median monthly baseline.

        Medians, not means, for the reason in specs/forecasting.md: one unusual month
        should not move the baseline it is being compared against.
        """
        names = {c.id: c.name for c in self._categories.list_for_user(user_id=user_id)}
        window_start = _months_ago(as_of, BASELINE_MONTHS)
        current_start = as_of.replace(day=1)

        history = self._transactions.for_user(
            user_id=user_id, since=window_start, until=as_of, limit=50_000
        )

        monthly: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        current: dict[UUID, Decimal] = defaultdict(Decimal)
        for txn in history:
            if txn.category_id is None or txn.transfer_group_id is not None:
                continue
            if txn.amount >= 0:
                continue  # income and refunds are not spending
            magnitude = -txn.amount
            key = f"{txn.occurred_on.year:04d}-{txn.occurred_on.month:02d}"
            if txn.occurred_on >= current_start:
                current[txn.category_id] += magnitude
            else:
                monthly[txn.category_id][key] += magnitude

        spends = []
        for category_id, per_month in monthly.items():
            values = sorted(per_month.values())
            if not values:
                continue
            midpoint = len(values) // 2
            baseline = (
                values[midpoint]
                if len(values) % 2 == 1
                else (values[midpoint - 1] + values[midpoint]) / Decimal("2")
            )
            spends.append(
                CategorySpend(
                    category=names.get(category_id, "Uncategorised"),
                    baseline_monthly=baseline,
                    current_monthly=current.get(category_id, Decimal("0")),
                )
            )
        return spends

    def _reconcile(self, *, user_id: UUID, finding: RiskFinding, as_of: date) -> None:
        """Deduplicate, suppress, or create — the lifecycle rules from the spec.

        - An active flag of the same type is updated in place, never duplicated.
        - A dismissed flag suppresses the same type for 30 days, unless the new finding's
          severity is higher, which overrides suppression.
        - An acknowledged flag is updated like an active one but keeps its status: the
          user has seen it, and re-raising it as new would undo that.
        """
        existing = self._flags.latest_of_type(
            user_id=user_id, risk_type=finding.risk_type.value
        )
        explanation = compose_explanation(finding)

        if existing is not None and existing.status is RiskStatus.DISMISSED:
            dismissed_at = existing.dismissed_at
            still_suppressed = (
                dismissed_at is not None
                and datetime.now(UTC) - dismissed_at
                < timedelta(days=DISMISSAL_SUPPRESSION_DAYS)
            )
            escalated = severity_rank(Severity(finding.severity.value)) > severity_rank(
                Severity(existing.severity)
            )
            if still_suppressed and not escalated:
                return

        if existing is not None and existing.status in (
            RiskStatus.ACTIVE,
            RiskStatus.ACKNOWLEDGED,
        ):
            existing.severity = finding.severity.value
            existing.detected_on = as_of
            existing.projected_date = finding.projected_date
            existing.quantified_amount = finding.quantified_amount
            existing.explanation = explanation
            existing.computation_reference = finding.computation_reference
            existing.details = finding.details
            return

        self._flags.add(
            RiskFlag(
                user_id=user_id,
                risk_type=finding.risk_type.value,
                severity=finding.severity.value,
                status=RiskStatus.ACTIVE,
                detected_on=as_of,
                projected_date=finding.projected_date,
                quantified_amount=finding.quantified_amount,
                explanation=explanation,
                computation_reference=finding.computation_reference,
                details=finding.details,
            )
        )

    def list_flags(self, *, user_id: UUID, status: RiskStatus | None) -> list[RiskFlag]:
        return self._flags.list_for_user(user_id=user_id, status=status)

    def acknowledge(self, flag_id: UUID, *, user_id: UUID) -> RiskFlag:
        flag = self._get(flag_id, user_id=user_id)
        flag.status = RiskStatus.ACKNOWLEDGED
        self._session.commit()
        return flag

    def dismiss(self, flag_id: UUID, *, user_id: UUID) -> RiskFlag:
        flag = self._get(flag_id, user_id=user_id)
        flag.status = RiskStatus.DISMISSED
        flag.dismissed_at = datetime.now(UTC)
        self._session.commit()
        return flag

    def _get(self, flag_id: UUID, *, user_id: UUID) -> RiskFlag:
        flag = self._flags.get_for_user(flag_id, user_id=user_id)
        if flag is None:
            raise NotFoundError("No risk flag with that identifier exists for this user.")
        return flag
