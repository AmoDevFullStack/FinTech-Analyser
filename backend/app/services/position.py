"""Position computation and the dashboard read path.

Per ADR-003 and specs/dashboard.md, `GET /position` reads stored results only and never
triggers computation — `capture_snapshot` is the one place a fresh position is computed,
called explicitly (`POST /position/snapshot`), by the forecast worker on a schedule, and
by scenario creation (which needs a snapshot to reference, per ADR-005).

Note on scope: `docs/database.md` models `Income`/`Expense`/`Debt`/`Asset` as entities
distinct from observed transactions. This "Now" slice does not build those tables (see
PLAN.md — full debt schedules, goals, and declared-vs-inferred income are "Next"); instead
monthly income/essential/discretionary are derived directly from the current month's
categorised transactions, and net worth/debt are derived from `Account` balances by type,
per specs/accounts.md "Aggregate position contributions grouped by type". Upcoming
obligations, the health score, and risk flags all depend on engines this slice does not
build, so they are returned empty/null and the dashboard renders their documented empty
states — this is the degrade path `specs/dashboard.md` itself specifies, not a shortcut.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession

from app.core.errors import NotFoundError
from app.domain.cash_flow import cash_flow_summary
from app.domain.emergency_fund import emergency_fund_months
from app.domain.net_worth import net_worth
from app.domain.projection import FinancialPosition
from app.models.account import Account, AccountType
from app.models.category import CategoryKind
from app.models.position_snapshot import PositionSnapshot
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.health_assessment import HealthAssessmentRepository
from app.repositories.position_snapshot import PositionSnapshotRepository
from app.repositories.transaction import TransactionRepository

LIQUID_TYPES = {AccountType.TRANSACTIONAL, AccountType.SAVINGS}
ASSET_TYPES = {
    AccountType.TRANSACTIONAL,
    AccountType.SAVINGS,
    AccountType.INVESTMENT,
    AccountType.MANUAL_ASSET,
}
DEBT_TYPES = {
    AccountType.CREDIT_CARD,
    AccountType.LOAN,
    AccountType.HOME_LOAN,
    AccountType.VEHICLE_FINANCE,
}


def _owed(account) -> Decimal:
    if account.account_type is AccountType.CREDIT_CARD:
        return max(Decimal("0"), -account.current_balance)
    return max(Decimal("0"), account.current_balance)


class PositionService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._snapshots = PositionSnapshotRepository(session)

    def compute_current(self, *, user_id: UUID, as_of: date | None = None) -> FinancialPosition:
        as_of = as_of or date.today()
        accounts = self._accounts.list_for_user(user_id=user_id)

        liquid_savings = sum(
            (a.current_balance for a in accounts if a.account_type in LIQUID_TYPES),
            Decimal("0"),
        )
        asset_values = [a.current_balance for a in accounts if a.account_type in ASSET_TYPES]
        debt_balances = [_owed(a) for a in accounts if a.account_type in DEBT_TYPES]
        total_debt = sum(debt_balances, Decimal("0"))
        computed_net_worth = net_worth(asset_values=asset_values, debt_balances=debt_balances)

        month_start = as_of.replace(day=1)
        sums = self.category_kind_sums(
            user_id=user_id, accounts=accounts, since=month_start, until=as_of
        )

        return FinancialPosition(
            as_of=as_of,
            liquid_savings=liquid_savings,
            total_debt=total_debt,
            net_worth=computed_net_worth,
            monthly_income=sums[CategoryKind.INCOME],
            monthly_essential=sums[CategoryKind.ESSENTIAL],
            monthly_discretionary=sums[CategoryKind.DISCRETIONARY],
        )

    def category_kind_sums(
        self, *, user_id: UUID, accounts: list[Account], since: date, until: date
    ) -> dict[CategoryKind, Decimal]:
        """Sum transaction amounts over a date range, grouped by category kind, excluding
        transfers. Shared by `compute_current` (current month, income/essential/
        discretionary) and `FinancialHealthService` (debt/saving kinds, and repeated per
        trailing month for the cash-flow-stability component).
        """
        categories = CategoryRepository(self._session)
        category_kind_by_id = {c.id: c.kind for c in categories.list_for_user(user_id=user_id)}

        sums: dict[CategoryKind, Decimal] = {kind: Decimal("0") for kind in CategoryKind}
        for account in accounts:
            for txn in self._transactions.by_account(
                account.id, user_id=user_id, since=since, until=until, limit=10_000
            ):
                if txn.transfer_group_id is not None or txn.category_id is None:
                    continue
                kind = category_kind_by_id.get(txn.category_id)
                if kind is None:
                    continue
                if kind is CategoryKind.INCOME:
                    # Signed, not magnitude: a negative "income" transaction (a reversal
                    # or correction) must reduce income, not add to it.
                    sums[kind] += txn.amount
                else:
                    # Essential/discretionary/debt/saving transactions are debits
                    # (negative amounts); reported as the positive magnitude spent/saved.
                    sums[kind] += -txn.amount if txn.amount < 0 else txn.amount
        return sums

    def capture_snapshot(self, *, user_id: UUID) -> PositionSnapshot:
        position = self.compute_current(user_id=user_id)
        cash_flow = cash_flow_summary(
            income=position.monthly_income,
            essential=position.monthly_essential,
            discretionary=position.monthly_discretionary,
        )
        fund_months = emergency_fund_months(
            liquid_savings=position.liquid_savings,
            monthly_essential_spending=position.monthly_essential,
        )

        snapshot = PositionSnapshot(
            user_id=user_id,
            captured_at=datetime.now(UTC),
            net_worth=position.net_worth,
            monthly_income=position.monthly_income,
            monthly_essential=position.monthly_essential,
            monthly_discretionary=position.monthly_discretionary,
            total_debt=position.total_debt,
            liquid_savings=position.liquid_savings,
            position={
                # health_score/health_generated_at deliberately absent here: dashboard_payload
                # reads those from the latest HealthAssessment directly, not from this
                # snapshot's frozen blob, since health is assessed on its own schedule
                # (specs/financial-health.md) independent of when a position was captured.
                "projected_cash_flow": str(cash_flow.remaining),
                "emergency_fund_months": str(fund_months),
                "upcoming_obligations": [],
                "active_risk_flags": 0,
            },
        )
        self._snapshots.add(snapshot)
        self._session.commit()
        return snapshot

    def dashboard_payload(self, *, user_id: UUID) -> dict:
        snapshot = self._snapshots.latest_for_user(user_id=user_id)
        if snapshot is None:
            return {
                "as_of": None,
                "net_worth": None,
                "liquid_savings": None,
                "total_debt": None,
                "monthly_income": None,
                "monthly_essential": None,
                "monthly_discretionary": None,
                "projected_cash_flow": None,
                "emergency_fund_months": None,
                "health_score": None,
                "health_generated_at": None,
                "health_score_change": None,
                "health_largest_negative_contributor": None,
                "upcoming_obligations": [],
                "active_risk_flags": 0,
                "is_stale": True,
            }

        extra = snapshot.position
        # limit=2: specs/dashboard.md region 4 wants a trend arrow and the single largest
        # contributing factor ON the dashboard, and the region's Inputs say the dashboard
        # issues exactly one API call — so both ride along in this one payload rather
        # than needing a second GET /health-assessment/history round trip.
        recent_health = HealthAssessmentRepository(self._session).history_for_user(
            user_id=user_id, limit=2
        )
        health = recent_health[0] if recent_health else None
        previous_health_score = recent_health[1].score if len(recent_health) > 1 else None

        return {
            "as_of": snapshot.captured_at.isoformat(),
            "net_worth": str(snapshot.net_worth),
            "liquid_savings": str(snapshot.liquid_savings),
            "total_debt": str(snapshot.total_debt),
            "monthly_income": str(snapshot.monthly_income),
            "monthly_essential": str(snapshot.monthly_essential),
            "monthly_discretionary": str(snapshot.monthly_discretionary),
            "projected_cash_flow": extra["projected_cash_flow"],
            "emergency_fund_months": extra["emergency_fund_months"],
            "health_score": health.score if health else None,
            "health_generated_at": health.computed_at.isoformat() if health else None,
            "health_score_change": (
                health.score - previous_health_score
                if health and previous_health_score is not None
                else None
            ),
            "health_largest_negative_contributor": (
                health.breakdown["largest_negative_contributor"] if health else None
            ),
            "upcoming_obligations": extra["upcoming_obligations"],
            "active_risk_flags": extra["active_risk_flags"],
            "is_stale": _is_stale(snapshot.captured_at),
        }

    def get_snapshot_for_user(self, snapshot_id: UUID, *, user_id: UUID) -> PositionSnapshot:
        snapshot = self._snapshots.get_for_user(snapshot_id, user_id=user_id)
        if snapshot is None:
            raise NotFoundError("No position snapshot with that identifier exists for this user.")
        return snapshot


def _is_stale(captured_at: datetime, *, max_age_hours: int = 24) -> bool:
    age = datetime.now(UTC) - captured_at
    return age.total_seconds() > max_age_hours * 3600
