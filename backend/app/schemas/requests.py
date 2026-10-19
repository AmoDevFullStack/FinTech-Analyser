"""Request models for the v1 API. One model per accepted shape; see app/schemas/base.py.

Conventions held to throughout:

  * Money and rates are `Decimal`, declared as such so pydantic parses the string the wire
    carries (ADR-001) and rejects anything that is not a number, rather than the route
    doing `Decimal(str(...))` and raising `InvalidOperation` into the 500 handler.
  * Every list endpoint bounds its `limit`. An unbounded limit is a table scan a client can
    ask for by accident.
  * `from` and `to` are date filters and `from` is a Python keyword, so the fields are
    named `since`/`until` and aliased to the wire names. The alias is the contract; the
    field name is an implementation detail of this file.
  * Semantic checks that need two fields together (a range whose end precedes its start)
    live in a `model_validator` here, not in the service, because they are statements about
    the request rather than about the user's money.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.models.debt import DebtType
from app.models.transaction import Direction
from app.domain.payment_taxonomy import PaymentMethod, SpendingPurpose
from app.schemas.base import ApiModel

NonEmptyString = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Email = Annotated[str, StringConstraints(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]

# Long enough to resist a dictionary attack, short enough that argon2 is not hashing a
# megabyte because someone posted a file into the field.
Password = Annotated[str, StringConstraints(min_length=12, max_length=256)]


class DateRangeMixin(ApiModel):
    since: date | None = Field(default=None, alias="from")
    until: date | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def _range_is_ordered(self):
        if self.since is not None and self.until is not None and self.until < self.since:
            raise ValueError("'to' must not precede 'from'")
        return self


# --------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------
class RegisterRequest(ApiModel):
    email: Email
    password: Password
    full_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class LoginRequest(ApiModel):
    email: Email
    # Not `Password`: a minimum length on login would reject the existing account of
    # anyone who registered before that rule, and tell an attacker the shape of the
    # password space for free.
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class RefreshRequest(ApiModel):
    refresh_token: NonEmptyString


# --------------------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------------------
#: `YYYY-MM`. A month key sorts and compares chronologically as plain text, which is why
#: the repository filters it with string comparisons rather than date casts.
MonthKey = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class HealthAssessmentQuery(ApiModel):
    """Filters for `GET /health-assessment`. No month asks for the most recent one."""

    month: MonthKey | None = None


class HealthMonthsQuery(ApiModel):
    """Filters for `GET /health-assessment/months`.

    `from`/`to` are months rather than dates here: the series is monthly, and a window that
    started mid-March would have to either include or exclude a month it only half covers.
    """

    since: MonthKey | None = Field(default=None, alias="from")
    until: MonthKey | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def _range_is_ordered(self):
        if self.since is not None and self.until is not None and self.until < self.since:
            raise ValueError("'to' must not precede 'from'")
        return self


class MonthlySummaryQuery(DateRangeMixin):
    """Filters for `GET /transactions/months`.

    `from` and `to` are dates rather than months, and are widened to whole calendar months
    by the service: a window is a set of months, and half of March is not one of them.
    Omitting both asks for the last twelve months.
    """

    account_id: UUID | None = None


class TransactionQuery(DateRangeMixin):
    """Filters for `GET /transactions`.

    `q` searches descriptions. `fuzzy` decides whether that search also returns rows whose
    description merely resembles the query, ranked by edit distance — see
    app/domain/text_match.py. It defaults on, because a user typing a merchant name into a
    search box means "find this merchant", and the statement spells that merchant three
    different ways.
    """

    account_id: UUID | None = None
    category_id: UUID | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    q: Annotated[str, StringConstraints(max_length=200)] | None = None
    fuzzy: bool = True
    # 0.62 admits one wrong character in a seven-letter merchant name and two in a longer
    # one, and excludes merchants that merely share a prefix. Exposed so a caller that
    # wants only near-exact matches can raise it without a new endpoint.
    min_score: Decimal = Field(default=Decimal("0.62"), ge=Decimal("0"), le=Decimal("1"))
    direction: Direction | None = None
    payment_method: PaymentMethod | None = None
    spending_purpose: SpendingPurpose | None = None
    is_recurring: bool | None = None
    uncategorised_only: bool = False
    limit: int = Field(default=50, ge=1, le=500)

    @model_validator(mode="after")
    def _amount_range_is_ordered(self):
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.max_amount < self.min_amount
        ):
            raise ValueError("'max_amount' must not be below 'min_amount'")
        return self


class ClassifyRequest(ApiModel):
    """Body for `POST /transactions/classify` — a dry run of the detection rules.

    Nothing is stored. This is what lets a client show "we read this as a rent debit order,
    essential, R14,500 a month" while the user is still typing, and what lets a reviewer
    check a rule without importing a file.
    """

    description: NonEmptyString
    amount: Decimal


class ManualTransactionRequest(ApiModel):
    """Body for `POST /transactions` — a single entry the user types in themselves.

    specs/transactions.md lists manual entry as an input alongside CSV. The same detection,
    deduplication, and impact reporting apply: one hand-entered R14,500 rent payment moves
    the same figures as an imported one.
    """

    account_id: UUID
    occurred_on: date
    amount: Decimal
    description: NonEmptyString
    category_id: UUID | None = None

    @field_validator("amount")
    @classmethod
    def _amount_is_not_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("amount must not be zero")
        return value


# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------
class ImportForm(ApiModel):
    """The multipart fields of `POST /imports`. The file itself is read from request.files."""

    account_id: UUID
    # A JSON object as a string, because it travels in a multipart form field. Parsed and
    # validated as `ColumnMappingRequest` by the route once it is known to be present.
    mapping: str | None = None
    # For a password-protected statement PDF, which is how several South African banks send
    # them. Used to open the file and never stored: it is the key to the document, and this
    # product has no reason to keep one.
    password: Annotated[str, StringConstraints(max_length=128)] | None = None


class ColumnMappingRequest(ApiModel):
    date_column: NonEmptyString
    description_column: NonEmptyString
    balance_column: str | None = None
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None

    @model_validator(mode="after")
    def _amount_is_derivable(self):
        if self.amount_column is None and self.debit_column is None and self.credit_column is None:
            raise ValueError(
                "supply 'amount_column', or 'debit_column' and 'credit_column'"
            )
        return self


class ConflictResolution(ApiModel):
    candidate_id: UUID
    action: Literal["import", "skip", "merge"]


class ResolveImportRequest(ApiModel):
    resolutions: list[ConflictResolution] = Field(min_length=1)


# --------------------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------------------
class CategoryCorrectionRequest(ApiModel):
    transaction_id: UUID
    category_id: UUID
    propagate: bool = True


# --------------------------------------------------------------------------------------
# Debts
# --------------------------------------------------------------------------------------
class CreateDebtRequest(ApiModel):
    debt_type: DebtType
    original_principal: Decimal = Field(ge=Decimal("0"))
    current_balance: Decimal = Field(ge=Decimal("0"))
    annual_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("2"))
    minimum_payment: Decimal = Field(gt=Decimal("0"))
    started_on: date
    account_id: UUID | None = None
    instalment: Decimal | None = Field(default=None, gt=Decimal("0"))
    term_months: int | None = Field(default=None, ge=1, le=600)

    @field_validator("term_months", mode="before")
    @classmethod
    def _blank_term_is_revolving(cls, value):
        """An empty string from a form field means "no term", not "term zero".

        docs/frontend.md §4 forbids the client from narrowing strings to numbers, so a
        cleared "term in months" input arrives as "". Coercing it here is the boundary's
        job; rejecting it would make a revolving facility impossible to record from the
        form that exists.
        """
        if value == "":
            return None
        return value


class UpdateDebtRequest(ApiModel):
    """Every field optional: an omitted field is left unchanged, a supplied one is set."""

    debt_type: DebtType | None = None
    current_balance: Decimal | None = Field(default=None, ge=Decimal("0"))
    annual_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("2"))
    minimum_payment: Decimal | None = Field(default=None, gt=Decimal("0"))
    instalment: Decimal | None = Field(default=None, gt=Decimal("0"))
    term_months: int | None = Field(default=None, ge=1, le=600)

    @field_validator("term_months", mode="before")
    @classmethod
    def _blank_term_is_revolving(cls, value):
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if all(getattr(self, name) is None for name in self.__class__.model_fields):
            raise ValueError("supply at least one field to change")
        return self


class ScheduleQuery(ApiModel):
    extra_monthly: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class WhatIfQuery(ApiModel):
    increments: list[Decimal] | None = None

    @field_validator("increments", mode="before")
    @classmethod
    def _split_csv(cls, value):
        """`?increments=100,500,1000` — one parameter, comma separated, as docs/api.md has it.

        Handles a list as well as a string because `parse_query` hands list-typed fields
        every repeated occurrence of the parameter. Both spellings therefore work:
        `increments=100,500` and `increments=100&increments=500`.
        """
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.extend(p.strip() for p in item.split(","))
                else:
                    parts.append(item)
            return [part for part in parts if part != ""]
        return value

    @field_validator("increments")
    @classmethod
    def _increments_are_positive(cls, value):
        if value is None:
            return value
        if not value:
            raise ValueError("supply at least one increment")
        for increment in value:
            if increment <= 0:
                raise ValueError(f"every increment must be positive, got {increment}")
        return value


class StrategiesQuery(ApiModel):
    total_monthly: Decimal | None = Field(default=None, gt=Decimal("0"))
    consolidation_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("2"))
    consolidation_fee: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
