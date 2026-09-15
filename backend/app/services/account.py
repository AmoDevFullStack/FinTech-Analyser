from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession

from app.core.errors import NotFoundError, ValidationError
from app.domain.net_worth import credit_utilisation
from app.models.account import Account, AccountType, BalanceSource
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository
from app.services.financial_health import FinancialHealthService
from app.services.position import PositionService

MANUAL_BALANCE_STALE_AFTER = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class CreateAccountInput:
    name: str
    account_type: AccountType
    institution: str | None
    opening_balance: Decimal
    opened_on: date | None
    interest_rate: Decimal | None = None
    credit_limit: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UpdateAccountInput:
    """Every field is optional and left unchanged when omitted, except `manual_balance`,
    which is rejected outright on a derived account — see specs/accounts.md's constraint
    that a derived balance is never overwritten by a manual entry.
    """

    name: str | None = None
    institution: str | None = None
    opened_on: date | None = None
    interest_rate: Decimal | None = None
    credit_limit: Decimal | None = None
    manual_balance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AccountView:
    account: Account
    balance: Decimal
    is_manual_balance_stale: bool
    utilisation: Decimal | None


class AccountService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._position = PositionService(session)
        self._health = FinancialHealthService(session)

    def _sync_position(self, user_id: UUID) -> None:
        """specs/financial-health.md: health is "computed by a worker on schedule and on
        material change" — an account mutation that moves a position figure is exactly
        that material change, so both the position snapshot and the health assessment are
        refreshed together here rather than only the snapshot.
        """
        self._position.capture_snapshot(user_id=user_id)
        self._health.assess(user_id=user_id)

    def create(self, *, user_id: UUID, data: CreateAccountInput) -> Account:
        account = Account(
            user_id=user_id,
            name=data.name,
            account_type=data.account_type,
            institution=data.institution,
            current_balance=data.opening_balance,
            balance_source=BalanceSource.MANUAL,
            manual_balance_set_at=datetime.now(UTC),
            interest_rate=data.interest_rate,
            credit_limit=data.credit_limit,
            opened_on=data.opened_on,
        )
        self._accounts.add(account)
        self._session.commit()
        self._sync_position(user_id)
        return account

    def list_for_user(self, *, user_id: UUID, include_archived: bool = False) -> list[AccountView]:
        accounts = self._accounts.list_for_user(user_id=user_id, include_archived=include_archived)
        return [self._view(account, user_id=user_id) for account in accounts]

    def get(self, account_id: UUID, *, user_id: UUID) -> AccountView:
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")
        return self._view(account, user_id=user_id)

    def update(self, account_id: UUID, *, user_id: UUID, data: UpdateAccountInput) -> Account:
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")

        if data.name is not None:
            account.name = data.name
        if data.institution is not None:
            account.institution = data.institution
        if data.opened_on is not None:
            account.opened_on = data.opened_on
        if data.interest_rate is not None:
            account.interest_rate = data.interest_rate
        if data.credit_limit is not None:
            account.credit_limit = data.credit_limit
        if data.manual_balance is not None:
            if account.balance_source is not BalanceSource.MANUAL:
                raise ValidationError(
                    "Balance is derived from transactions and cannot be edited directly. "
                    "Correct the transactions instead."
                )
            account.current_balance = data.manual_balance
            account.manual_balance_set_at = datetime.now(UTC)

        self._session.commit()
        # Only a balance or credit-limit edit moves a figure the dashboard or the health
        # score shows — renaming an account or changing its institution or interest rate
        # doesn't — so the resync is only worth doing here.
        if data.manual_balance is not None or data.credit_limit is not None:
            self._sync_position(user_id)
        return account

    def archive(self, account_id: UUID, *, user_id: UUID) -> Account:
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")
        account.archived_at = datetime.now(UTC)
        self._session.commit()
        self._sync_position(user_id)
        return account

    def soft_delete(self, account_id: UUID, *, user_id: UUID) -> None:
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")
        account.deleted_at = datetime.now(UTC)
        self._session.commit()
        self._sync_position(user_id)

    def recompute_derived_balance(self, account_id: UUID, *, user_id: UUID) -> Account:
        """A derived balance is never maintained incrementally — it is recomputed in full
        whenever the account's transactions change. See specs/accounts.md.
        """
        account = self._accounts.get_for_user(account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")
        if account.balance_source is BalanceSource.DERIVED:
            total = self._transactions.sum_by_account(account_id, user_id=user_id)
            account.current_balance = total
            self._session.commit()
            self._sync_position(user_id)
        return account

    def _view(self, account: Account, *, user_id: UUID) -> AccountView:
        is_stale = (
            account.balance_source is BalanceSource.MANUAL
            and account.manual_balance_set_at is not None
            and datetime.now(UTC) - account.manual_balance_set_at > MANUAL_BALANCE_STALE_AFTER
        )
        utilisation = None
        if account.account_type is AccountType.CREDIT_CARD and account.credit_limit:
            utilisation = credit_utilisation(
                balance_owed=-account.current_balance
                if account.current_balance < 0
                else account.current_balance,
                credit_limit=account.credit_limit,
            )
        return AccountView(
            account=account,
            balance=account.current_balance,
            is_manual_balance_stale=is_stale,
            utilisation=utilisation,
        )
