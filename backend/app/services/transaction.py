"""Single-transaction entry and the read path around it. See specs/transactions.md.

The spec lists "manual entry for a single transaction" alongside CSV import as an input,
and until now only the CSV path existed. A hand-entered rent payment has to go through the
same pipeline as an imported one — normalisation, the exact-duplicate fingerprint,
detection, categorisation, and the same recomputation of everything downstream — or the
two paths produce different figures for the same payment, and which one a user gets
depends on how they happened to enter it.

There is no staging step here. Staging exists because a CSV arrives as hundreds of rows a
user has not seen; one row they typed themselves is already reviewed. The impact report is
still returned, because the effect on their cash flow is not something they can see by
looking at the row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.db import DbSession
from app.core.errors import ConflictError, NotFoundError
from app.core.events import TRANSACTION_CREATED, dispatch_pending, record
from app.models.transaction import Direction, Transaction
from app.repositories.account import AccountRepository
from app.repositories.category import CategoryRepository
from app.repositories.transaction import TransactionRepository
from app.services.categorisation import CategorisationService
from app.services.import_service import make_fingerprint, normalise_description
from app.services.recurrence import RecurrenceService
from app.services.spending_insight import SpendingInsight, SpendingInsightService


@dataclass(frozen=True, slots=True)
class ManualTransactionInput:
    account_id: UUID
    occurred_on: date
    amount: Decimal
    description: str
    category_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreatedTransaction:
    transaction: Transaction
    insight: SpendingInsight


class TransactionService:
    def __init__(self, session: DbSession) -> None:
        self._session = session
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)
        self._categories = CategoryRepository(session)
        self._categorisation = CategorisationService(session)
        self._insight = SpendingInsightService(session)

    def create(self, *, user_id: UUID, data: ManualTransactionInput) -> CreatedTransaction:
        """Record one transaction and report what it changed.

        A fingerprint collision raises `ConflictError` rather than being skipped silently
        the way an imported duplicate is. The two are different events: a duplicate row in
        a 600-row CSV is the file's fault and counting it is the right response, while a
        user typing the same payment twice wants to be told, not to have their second
        attempt quietly discarded.
        """
        account = self._accounts.get_for_user(data.account_id, user_id=user_id)
        if account is None:
            raise NotFoundError("No account with that identifier exists for this user.")

        normalised = normalise_description(data.description)
        fingerprint = make_fingerprint(
            user_id=user_id,
            account_id=data.account_id,
            occurred_on=data.occurred_on,
            amount=data.amount,
            normalised=normalised,
        )
        if self._transactions.fingerprint_exists(fingerprint, user_id=user_id):
            raise ConflictError(
                "An identical transaction on that date, for that amount, already exists."
            )

        transaction = Transaction(
            user_id=user_id,
            account_id=data.account_id,
            occurred_on=data.occurred_on,
            amount=data.amount,
            description=data.description,
            normalised_description=normalised,
            direction=Direction.CREDIT if data.amount >= 0 else Direction.DEBIT,
            fingerprint=fingerprint,
        )
        self._insight.classify_transaction(transaction)

        if data.category_id is not None:
            # A category the user chose is a correction from the moment it is made, and
            # must survive every later automatic pass — specs/transactions.md step 5.
            transaction.category_id = data.category_id
            transaction.category_set_by_user = True
            transaction.category_confidence = Decimal("1.000000")
        else:
            suggestion = self._categorisation.suggest(
                normalised_description=normalised,
                categories=self._categories.list_for_user(user_id=user_id),
                corrections=self._categorisation.corrected_history(user_id=user_id),
                amount=data.amount,
            )
            if suggestion.category is not None:
                transaction.category_id = suggestion.category.id
                transaction.category_confidence = suggestion.confidence

        # Before the row is added, deliberately. The impact report reads the user's
        # existing transactions to build its "before" side, and a flushed row is visible to
        # that read inside the same session — computing afterwards would put this
        # transaction on both sides of the comparison and report a delta of zero.
        insight = self._insight.insight_for_transactions(
            user_id=user_id,
            account_id=data.account_id,
            transactions=[transaction],
        )

        self._transactions.add(transaction)
        self._session.flush()
        RecurrenceService(self._session).apply(user_id=user_id)
        # The same event an import commit records, and so the same recomputation: a single
        # transaction moves the figures a hundred of them do, only by less. Keeping the two
        # paths behind one event is what stops them drifting apart again — they did before,
        # and the manual path was the one that happened to be more complete.
        record(
            self._session,
            user_id=user_id,
            name=TRANSACTION_CREATED,
            payload={
                "transaction_id": str(transaction.id),
                "account_id": str(data.account_id),
                "amount": str(data.amount),
                "occurred_on": data.occurred_on.isoformat(),
            },
        )
        self._session.commit()

        dispatch_pending(self._session, user_id=user_id)

        return CreatedTransaction(transaction=transaction, insight=insight)

    def get(self, transaction_id: UUID, *, user_id: UUID) -> Transaction:
        transaction = self._transactions.get_for_user(transaction_id, user_id=user_id)
        if transaction is None:
            raise NotFoundError("No transaction with that identifier exists for this user.")
        return transaction
