"""What a payment was, and what it was for. See specs/transactions.md steps 2 and 5.

A bank statement line carries two independent facts that the rest of the system needs
kept apart:

  * **How** the money moved — a debit order, a card swipe, an ATM withdrawal, an EFT.
    This is the payment *method*, and it is the strongest available evidence about whether
    a payment will happen again next month. A debit order is a contract; a card purchase
    is a decision.
  * **What** it was for — rent, groceries, a medical aid premium, a loan instalment. This
    is the *purpose*, and it is what decides whether the money was essential, discretionary,
    debt service, saving, or income, which in turn decides every cash-flow figure
    downstream.

Conflating the two loses information in both directions. "DEBIT ORDER: DISCOVERY LIFE" is
a recurring essential; "CARD PURCHASE: DISCOVERY STORE" is discretionary; the merchant
token is nearly the same and the method is what separates them.

This engine is pure and deterministic: descriptions and an amount in, a classification
out. It knows nothing about a user's history — `app/services/categorisation.py` is where
this engine's opinion is weighed against what the user has actually corrected, and a user
correction always wins.

Rule coverage is South African retail banking, matching the banks specs/transactions.md
names. It is a vocabulary, not a model: every rule here is a literal statement about what
a phrase means on a statement, and an unrecognised description resolves to UNKNOWN rather
than to a guess.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.text_match import levenshtein_ratio, tokenise


class PaymentMethod(str, enum.Enum):
    """How the money moved. Values match the `payment_method_enum` Postgres type."""

    DEBIT_ORDER = "debit_order"
    STOP_ORDER = "stop_order"
    CARD_PURCHASE = "card_purchase"
    CARD_ONLINE = "card_online"
    ATM_WITHDRAWAL = "atm_withdrawal"
    CASH_DEPOSIT = "cash_deposit"
    EFT_OUT = "eft_out"
    EFT_IN = "eft_in"
    INSTANT_PAYMENT = "instant_payment"
    INTERNAL_TRANSFER = "internal_transfer"
    SALARY_DEPOSIT = "salary_deposit"
    CHEQUE = "cheque"
    BANK_FEE = "bank_fee"
    INTEREST = "interest"
    REVERSAL = "reversal"
    UNKNOWN = "unknown"

    @property
    def is_committed(self) -> bool:
        """Whether this method implies a standing arrangement rather than a decision.

        A debit order, stop order, or salary deposit repeats because something outside the
        month says it must. The projection treats those as commitments even before
        recurrence detection has three occurrences to work with — see
        specs/transactions.md step 6 for why that threshold exists and why a method-level
        signal is useful before it is met.
        """
        return self in {
            PaymentMethod.DEBIT_ORDER,
            PaymentMethod.STOP_ORDER,
            PaymentMethod.SALARY_DEPOSIT,
        }


class SpendKind(str, enum.Enum):
    """What a purpose does to cash flow.

    Mirrors `app/models/category.py`'s `CategoryKind` value-for-value on purpose: domain
    modules may not import models, and services map between the two by `.value`. If a kind
    is added to one, add it to the other.
    """

    INCOME = "income"
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"
    DEBT = "debt"
    SAVING = "saving"
    TRANSFER = "transfer"


class SpendingPurpose(str, enum.Enum):
    """What the payment was for. Values match the `spending_purpose_enum` Postgres type."""

    RENT = "rent"
    BOND_REPAYMENT = "bond_repayment"
    LEVIES = "levies"
    RATES_AND_TAXES = "rates_and_taxes"
    UTILITIES = "utilities"
    GROCERIES = "groceries"
    FUEL = "fuel"
    TRANSPORT = "transport"
    VEHICLE_INSTALMENT = "vehicle_instalment"
    INSURANCE = "insurance"
    MEDICAL = "medical"
    TELECOMS = "telecoms"
    SUBSCRIPTIONS = "subscriptions"
    DINING = "dining"
    ENTERTAINMENT = "entertainment"
    CLOTHING = "clothing"
    EDUCATION = "education"
    CHILDCARE = "childcare"
    DOMESTIC_HELP = "domestic_help"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    DEBT_REPAYMENT = "debt_repayment"
    BANK_CHARGES = "bank_charges"
    SALARY = "salary"
    OTHER_INCOME = "other_income"
    INTERNAL_TRANSFER = "internal_transfer"
    UNKNOWN = "unknown"


PURPOSE_KIND: dict[SpendingPurpose, SpendKind] = {
    # Housing. Rent and a bond instalment are both the roof over someone's head and both
    # essential, but they are separate purposes because only one of them builds equity and
    # only one of them is a debt the payoff engines can schedule.
    SpendingPurpose.RENT: SpendKind.ESSENTIAL,
    SpendingPurpose.BOND_REPAYMENT: SpendKind.DEBT,
    SpendingPurpose.LEVIES: SpendKind.ESSENTIAL,
    SpendingPurpose.RATES_AND_TAXES: SpendKind.ESSENTIAL,
    SpendingPurpose.UTILITIES: SpendKind.ESSENTIAL,
    SpendingPurpose.GROCERIES: SpendKind.ESSENTIAL,
    SpendingPurpose.FUEL: SpendKind.ESSENTIAL,
    SpendingPurpose.TRANSPORT: SpendKind.ESSENTIAL,
    SpendingPurpose.VEHICLE_INSTALMENT: SpendKind.DEBT,
    SpendingPurpose.INSURANCE: SpendKind.ESSENTIAL,
    SpendingPurpose.MEDICAL: SpendKind.ESSENTIAL,
    SpendingPurpose.TELECOMS: SpendKind.ESSENTIAL,
    SpendingPurpose.EDUCATION: SpendKind.ESSENTIAL,
    SpendingPurpose.CHILDCARE: SpendKind.ESSENTIAL,
    SpendingPurpose.DOMESTIC_HELP: SpendKind.ESSENTIAL,
    SpendingPurpose.SUBSCRIPTIONS: SpendKind.DISCRETIONARY,
    SpendingPurpose.DINING: SpendKind.DISCRETIONARY,
    SpendingPurpose.ENTERTAINMENT: SpendKind.DISCRETIONARY,
    SpendingPurpose.CLOTHING: SpendKind.DISCRETIONARY,
    SpendingPurpose.SAVINGS: SpendKind.SAVING,
    SpendingPurpose.INVESTMENT: SpendKind.SAVING,
    SpendingPurpose.DEBT_REPAYMENT: SpendKind.DEBT,
    # A bank charge is unavoidable while the account is open, so it is essential rather
    # than discretionary — a user cannot decide not to pay it this month.
    SpendingPurpose.BANK_CHARGES: SpendKind.ESSENTIAL,
    SpendingPurpose.SALARY: SpendKind.INCOME,
    SpendingPurpose.OTHER_INCOME: SpendKind.INCOME,
    SpendingPurpose.INTERNAL_TRANSFER: SpendKind.TRANSFER,
}

PURPOSE_CATEGORY_NAME: dict[SpendingPurpose, str] = {
    SpendingPurpose.RENT: "Rent",
    SpendingPurpose.BOND_REPAYMENT: "Bond repayment",
    SpendingPurpose.LEVIES: "Levies",
    SpendingPurpose.RATES_AND_TAXES: "Rates and taxes",
    SpendingPurpose.UTILITIES: "Utilities",
    SpendingPurpose.GROCERIES: "Groceries",
    SpendingPurpose.FUEL: "Fuel",
    SpendingPurpose.TRANSPORT: "Transport",
    SpendingPurpose.VEHICLE_INSTALMENT: "Vehicle instalment",
    SpendingPurpose.INSURANCE: "Insurance",
    SpendingPurpose.MEDICAL: "Medical",
    SpendingPurpose.TELECOMS: "Telecoms",
    SpendingPurpose.SUBSCRIPTIONS: "Subscriptions",
    SpendingPurpose.DINING: "Dining out",
    SpendingPurpose.ENTERTAINMENT: "Entertainment",
    SpendingPurpose.CLOTHING: "Clothing",
    SpendingPurpose.EDUCATION: "Education",
    SpendingPurpose.CHILDCARE: "Childcare",
    SpendingPurpose.DOMESTIC_HELP: "Domestic help",
    SpendingPurpose.SAVINGS: "Savings",
    SpendingPurpose.INVESTMENT: "Investment",
    SpendingPurpose.DEBT_REPAYMENT: "Debt repayment",
    SpendingPurpose.BANK_CHARGES: "Bank charges",
    SpendingPurpose.SALARY: "Salary",
    SpendingPurpose.OTHER_INCOME: "Other income",
    SpendingPurpose.INTERNAL_TRANSFER: "Transfer",
}

CONFIDENCE_PHRASE = Decimal("0.900000")  # an unambiguous statement phrase, e.g. "debit order"
CONFIDENCE_MERCHANT = Decimal("0.800000")  # a named merchant whose trade is known
CONFIDENCE_FUZZY = Decimal("0.650000")  # a merchant recognised through a misspelling
CONFIDENCE_SIGN_ONLY = Decimal("0.400000")  # nothing but the direction of the amount
CONFIDENCE_NONE = Decimal("0.000000")

# A statement token has to be at least this close to a known merchant token before a
# misspelling is treated as that merchant. Below it, two names sharing a few letters are
# two names.
FUZZY_MERCHANT_THRESHOLD = Decimal("0.82")
_MIN_FUZZY_TOKEN_LENGTH = 5  # shorter tokens are too easy to mutate into each other


def _rule(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# --------------------------------------------------------------------------------------
# Method rules. Ordered: the first match wins, so the more specific phrase comes first.
# "debit order" must beat the bare "debit" that a card rule would otherwise claim.
# --------------------------------------------------------------------------------------
_METHOD_RULES: tuple[tuple[re.Pattern[str], PaymentMethod], ...] = (
    (_rule(r"\b(?:debit\s*order|d[/\s]*order|deb\s*ord|do\s*pmt|magtape)\b"), PaymentMethod.DEBIT_ORDER),
    (_rule(r"\b(?:stop\s*order|s[/\s]*order|stop\s*ord|standing\s*order)\b"), PaymentMethod.STOP_ORDER),
    (_rule(r"\b(?:reversal|reversed|refund|rtn\s*debit|unpaid\s*debit)\b"), PaymentMethod.REVERSAL),
    (_rule(r"\b(?:salary|salaris|payroll|wages|sal\s*dep)\b"), PaymentMethod.SALARY_DEPOSIT),
    (
        _rule(r"\b(?:atm|autobank|cash\s*withdrawal|withdrawal\s*atm|geldoutomaat)\b"),
        PaymentMethod.ATM_WITHDRAWAL,
    ),
    (_rule(r"\b(?:cash\s*dep(?:osit)?|deposit\s*cash|cdm)\b"), PaymentMethod.CASH_DEPOSIT),
    (
        _rule(r"\b(?:online\s*purch(?:ase)?|internet\s*purch(?:ase)?|e[\s-]*com(?:merce)?|card\s*not\s*present|cnp)\b"),
        PaymentMethod.CARD_ONLINE,
    ),
    (
        _rule(r"\b(?:pos\s*purch(?:ase)?|card\s*purch(?:ase)?|purch(?:ase)?\s*card|chip\s*(?:and|&)\s*pin|contactless|tap\s*(?:and|&)\s*go|debit\s*card|credit\s*card\s*purch)\b"),
        PaymentMethod.CARD_PURCHASE,
    ),
    (
        _rule(r"\b(?:payshap|rtc|real\s*time\s*clearing|immediate\s*pay(?:ment)?|instant\s*pay(?:ment)?)\b"),
        PaymentMethod.INSTANT_PAYMENT,
    ),
    (
        _rule(r"\b(?:transfer|trf|tfr|inter[\s-]*account|own\s*account|oorplasing)\b"),
        PaymentMethod.INTERNAL_TRANSFER,
    ),
    (_rule(r"\bcheque\b|\bcheq\b|\bchq\b"), PaymentMethod.CHEQUE),
    (
        _rule(r"\b(?:service\s*fee|monthly\s*fee|account\s*fee|admin\s*fee|bank\s*charge|card\s*fee|fees?)\b"),
        PaymentMethod.BANK_FEE,
    ),
    (_rule(r"\b(?:interest|rente)\b"), PaymentMethod.INTEREST),
    (
        _rule(r"\b(?:eft|electronic\s*(?:funds\s*)?transfer|ib\s*pay(?:ment)?|internet\s*bank(?:ing)?|payment\s*(?:to|from)|betaling)\b"),
        PaymentMethod.EFT_OUT,
    ),
)


# --------------------------------------------------------------------------------------
# Purpose rules. Ordered most specific first. A phrase rule ("body corporate") outranks a
# merchant rule ("checkers") outranks a bare keyword ("rent"), because a merchant name can
# appear inside a longer phrase that means something else.
# --------------------------------------------------------------------------------------
_PURPOSE_RULES: tuple[tuple[re.Pattern[str], SpendingPurpose, Decimal], ...] = (
    # Housing — checked before everything else, because "rent" and "bond" are the two
    # largest lines in most South African budgets and the two most costly to miscategorise.
    (
        _rule(r"\b(?:rent(?:al)?|huur|landlord|verhuurder|lease\s*pay|tenant|accommodation)\b"),
        SpendingPurpose.RENT,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:bond|home\s*loan|mortgage|verband|huislening|sa\s*home\s*loans|ooba)\b"),
        SpendingPurpose.BOND_REPAYMENT,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:body\s*corporate|levy|levies|hoa|home\s*owners?\s*assoc|sectional\s*title)\b"),
        SpendingPurpose.LEVIES,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:municipal(?:ity)?|rates\s*(?:and|&)\s*taxes|city\s*of\s+\w+|joburg|tshwane|ekurhuleni|ethekwini|mangaung|nelson\s*mandela\s*bay|sars|traffic\s*fine)\b"),
        SpendingPurpose.RATES_AND_TAXES,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:eskom|electricity|prepaid\s*elec|water\s*(?:and|&)\s*sanitation|refuse|sewerage|utilit(?:y|ies)|gas\b)\b"),
        SpendingPurpose.UTILITIES,
        CONFIDENCE_PHRASE,
    ),
    # Debt, before the merchants that also lend. "capitec loan" is debt service; "capitec"
    # alone is just the bank the account is at.
    (
        _rule(r"\b(?:wesbank|mfc\b|motor\s*finance|vehicle\s*finance|toyota\s*financial|vw\s*financial|bmw\s*financial|ford\s*credit|instal?ment\s*sale)\b"),
        SpendingPurpose.VEHICLE_INSTALMENT,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:loan\s*(?:repay(?:ment)?|instal?ment|pay(?:ment)?)|personal\s*loan|credit\s*card\s*pay(?:ment)?|card\s*repay|african\s*bank|bayport|direct\s*axis|finchoice|wonga|store\s*card|account\s*pay(?:ment)?\s*(?:edgars|truworths|foschini))\b"),
        SpendingPurpose.DEBT_REPAYMENT,
        CONFIDENCE_PHRASE,
    ),
    # Insurance and medical, before retail: "dis-chem" is medical, "discovery insure" is
    # insurance, and both would otherwise be swept up by a generic merchant rule.
    (
        _rule(r"\b(?:insur(?:e|ance)|assurance|outsurance|santam|hollard|miway|king\s*price|naked\s*insur|budget\s*insur|old\s*mutual|sanlam|liberty|funeral\s*(?:cover|plan|policy)|life\s*cover|short\s*term\s*insur)\b"),
        SpendingPurpose.INSURANCE,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:medical\s*aid|discovery\s*health|momentum\s*health|bonitas|medshield|gems\b|fedhealth|bestmed|pharmacy|dis[\s-]*chem|clicks|netcare|mediclinic|life\s*health|hospital|doctor|dentist|optometrist|radiolog|patholog)\b"),
        SpendingPurpose.MEDICAL,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:vodacom|mtn\b|cell\s*c|telkom|rain\b|afrihost|webafrica|mweb|cool\s*ideas|vumatel|openserve|fibre|airtime|data\s*bundle|prepaid\s*airtime)\b"),
        SpendingPurpose.TELECOMS,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:netflix|spotify|showmax|dstv|multichoice|apple\.com|itunes|icloud|google\s*(?:play|storage|one)|microsoft|office\s*365|prime\s*video|amazon\s*prime|youtube|audible|canva|adobe|subscription|membership|gym|virgin\s*active|planet\s*fitness)\b"),
        SpendingPurpose.SUBSCRIPTIONS,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:checkers|shoprite|pick\s*n\s*pay|pnp\b|woolworths|woolies|spar\b|food\s*lover|fruit\s*(?:and|&)\s*veg|makro|usave|boxer|cambridge\s*food|grocer(?:y|ies)|supermarket)\b"),
        SpendingPurpose.GROCERIES,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:engen|sasol|caltex|astron|total\s*(?:garage|energies)?|shell|bp\b|puma\s*energy|petrol|diesel|fuel|garage|forecourt)\b"),
        SpendingPurpose.FUEL,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:uber(?!\s*eats)|bolt\b|gautrain|metrorail|taxi|e[\s-]*toll|sanral|parking|licen[cs]e\s*(?:disc|renewal)|putco|intercape|greyhound)\b"),
        SpendingPurpose.TRANSPORT,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:uber\s*eats|mr\s*d\b|nando|kfc|mcdonald|steers|wimpy|debonairs|romans\s*pizza|spur\b|ocean\s*basket|rocomamas|starbucks|vida\s*e|seattle\s*coffee|mugg\s*(?:and|&)\s*bean|restaurant|takeaway|coffee|cafe|bistro)\b"),
        SpendingPurpose.DINING,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:ster[\s-]*kinekor|nu\s*metro|computicket|quicket|tops\b|liquor|bottle\s*store|makro\s*liquor|casino|betway|hollywoodbets|lotto|cinema|theatre)\b"),
        SpendingPurpose.ENTERTAINMENT,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:truworths|mr\s*price|foschini|edgars|ackermans|pep\b|cotton\s*on|h\s*(?:and|&)\s*m|zara|sportscene|totalsports|markham|exact\b|jet\b|clothing|boutique)\b"),
        SpendingPurpose.CLOTHING,
        CONFIDENCE_MERCHANT,
    ),
    (
        _rule(r"\b(?:cr[eè]che|day\s*care|aftercare|after\s*care|nanny|au\s*pair|play\s*school)\b"),
        SpendingPurpose.CHILDCARE,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:school\s*fees?|tuition|universit(?:y|eit)|unisa|wits|stellenbosch|tvet|college|bursary|textbook|nsfas|education)\b"),
        SpendingPurpose.EDUCATION,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:domestic\s*(?:worker|help)|gardener|cleaner|housekeep|sweeper)\b"),
        SpendingPurpose.DOMESTIC_HELP,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:easy\s*equities|allan\s*gray|coronation|satrix|sygnia|10x\b|ninety\s*one|prescient|unit\s*trust|retirement\s*annuity|\bra\s*contribution|provident\s*fund|pension\s*fund|investment|etf\b|brokerage)\b"),
        SpendingPurpose.INVESTMENT,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:savings?\s*(?:account|transfer|deposit|pocket)?|goalsave|goal\s*save|tax\s*free\s*savings|tfsa|32\s*day|notice\s*(?:account|deposit)|emergency\s*fund|stokvel)\b"),
        SpendingPurpose.SAVINGS,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:service\s*fee|monthly\s*(?:account\s*)?fee|account\s*fee|admin\s*fee|bank\s*charge|card\s*fee|cash\s*(?:handling|withdrawal)\s*fee|penalty\s*fee|honouring\s*fee|unpaid\s*fee)\b"),
        SpendingPurpose.BANK_CHARGES,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:salary|salaris|payroll|wages|remuneration|sal\s*dep)\b"),
        SpendingPurpose.SALARY,
        CONFIDENCE_PHRASE,
    ),
    (
        _rule(r"\b(?:dividend|interest\s*(?:earned|credit(?:ed)?)|rent(?:al)?\s*income|commission|bonus|refund|sassa|grant|tax\s*refund)\b"),
        SpendingPurpose.OTHER_INCOME,
        CONFIDENCE_PHRASE,
    ),
)

# Single-token merchant vocabulary for the misspelling pass. Only tokens long enough that
# an edit-distance match means something appear here; "bp" and "mtn" are matched by the
# regex rules above or not at all.
_FUZZY_MERCHANT_TOKENS: tuple[tuple[str, SpendingPurpose], ...] = (
    ("woolworths", SpendingPurpose.GROCERIES),
    ("woolies", SpendingPurpose.GROCERIES),
    ("checkers", SpendingPurpose.GROCERIES),
    ("shoprite", SpendingPurpose.GROCERIES),
    ("boxer", SpendingPurpose.GROCERIES),
    ("makro", SpendingPurpose.GROCERIES),
    ("engen", SpendingPurpose.FUEL),
    ("caltex", SpendingPurpose.FUEL),
    ("sasol", SpendingPurpose.FUEL),
    ("astron", SpendingPurpose.FUEL),
    ("petrol", SpendingPurpose.FUEL),
    ("garage", SpendingPurpose.FUEL),
    ("netflix", SpendingPurpose.SUBSCRIPTIONS),
    ("spotify", SpendingPurpose.SUBSCRIPTIONS),
    ("showmax", SpendingPurpose.SUBSCRIPTIONS),
    ("multichoice", SpendingPurpose.SUBSCRIPTIONS),
    ("vodacom", SpendingPurpose.TELECOMS),
    ("telkom", SpendingPurpose.TELECOMS),
    ("afrihost", SpendingPurpose.TELECOMS),
    ("vumatel", SpendingPurpose.TELECOMS),
    ("outsurance", SpendingPurpose.INSURANCE),
    ("santam", SpendingPurpose.INSURANCE),
    ("hollard", SpendingPurpose.INSURANCE),
    ("discovery", SpendingPurpose.MEDICAL),
    ("bonitas", SpendingPurpose.MEDICAL),
    ("medshield", SpendingPurpose.MEDICAL),
    ("pharmacy", SpendingPurpose.MEDICAL),
    ("mediclinic", SpendingPurpose.MEDICAL),
    ("truworths", SpendingPurpose.CLOTHING),
    ("foschini", SpendingPurpose.CLOTHING),
    ("ackermans", SpendingPurpose.CLOTHING),
    ("sportscene", SpendingPurpose.CLOTHING),
    ("wesbank", SpendingPurpose.VEHICLE_INSTALMENT),
    ("eskom", SpendingPurpose.UTILITIES),
    ("municipality", SpendingPurpose.RATES_AND_TAXES),
    ("rental", SpendingPurpose.RENT),
    ("landlord", SpendingPurpose.RENT),
    ("mortgage", SpendingPurpose.BOND_REPAYMENT),
    ("salary", SpendingPurpose.SALARY),
)

# Tokens that describe the mechanics of a payment rather than who was paid. Stripping them
# is what turns "pos purchase 1234 woolworths claremont" into "woolworths claremont".
_MECHANICAL_TOKENS: frozenset[str] = frozenset(
    {
        "pos", "purchase", "purch", "card", "debit", "credit", "order", "stop", "standing",
        "atm", "autobank", "cash", "withdrawal", "deposit", "eft", "transfer", "trf", "tfr",
        "payment", "pay", "pmt", "ref", "reference", "fee", "fees", "charge", "charges",
        "internet", "banking", "ib", "online", "contactless", "tap", "chip", "pin", "cheque",
        "chq", "immediate", "instant", "rtc", "payshap", "magtape", "inter", "account",
        "acc", "to", "from", "the", "and", "of", "za", "sa", "zar", "rand", "cnp", "ecom",
        "sbsa", "fnb", "absa", "nedbank", "capitec", "tymebank", "discovery bank",
    }
)


@dataclass(frozen=True, slots=True)
class PaymentClassification:
    """What one statement line was, and how sure this engine is of each half.

    `method_confidence` and `purpose_confidence` are separate because the two halves are
    decided by separate evidence and are wrong independently: "DEBIT ORDER 4471992" is a
    certain method and an unknown purpose, and neither figure should borrow the other's
    credibility.
    """

    method: PaymentMethod
    purpose: SpendingPurpose
    kind: SpendKind | None
    merchant: str | None
    method_confidence: Decimal
    purpose_confidence: Decimal
    matched_rule: str


def extract_merchant(description: str) -> str | None:
    """The counterparty in a statement description, with the payment mechanics removed.

    Formula:
        Tokenise, drop tokens that are purely numeric, shorter than two characters, or in
        the mechanical vocabulary, then re-join with single spaces.

    Assumptions:
        - Reference numbers are noise. `normalise_description` in the import service
          already strips runs of four or more digits; this drops the shorter ones a card
          suffix leaves behind.
        - Returns None rather than an empty string when nothing survives, so a caller
          storing this cannot accidentally persist "" as a merchant name.
        - The bank's own name is mechanical, not a counterparty: "FNB APP PAYMENT FROM
          NADIA" was paid by Nadia, not by FNB.

    Rounding:
        Not applicable.

    Raises:
        Nothing.
    """
    kept = [
        token
        for token in tokenise(description)
        if len(token) > 1 and not token.isdigit() and token not in _MECHANICAL_TOKENS
    ]
    return " ".join(kept) or None


def classify_method(description: str, *, amount: Decimal) -> tuple[PaymentMethod, Decimal, str]:
    """Decide how the money moved, from the description's mechanical phrases and the sign.

    Formula:
        The first matching rule in `_METHOD_RULES` wins. Direction-ambiguous results are
        then resolved by the sign of `amount`: an EFT rule matched on an inflow is EFT_IN,
        and a salary rule matched on an outflow is not a salary deposit at all, so it
        falls back to the generic EFT for its direction.

    Assumptions:
        - Sign follows docs/database.md §3 without exception: outflow negative, inflow
          positive. A zero amount is treated as an outflow, because a zero-value line is a
          fee reversal or an authorisation and never an income event.
        - An unrecognised description still yields a direction-only answer rather than
          UNKNOWN, since the sign alone is real evidence and refusing to use it would make
          every unmapped bank format classify as nothing.

    Rounding:
        Confidence is a fixed six-place constant, not computed.

    Raises:
        Nothing.
    """
    is_inflow = amount > 0

    for pattern, method in _METHOD_RULES:
        if not pattern.search(description):
            continue
        if method is PaymentMethod.SALARY_DEPOSIT and not is_inflow:
            # "SALARY TRANSFER TO SAVINGS" is not income; it is the user moving their
            # salary somewhere. The word is present, the direction says it is not a deposit.
            return PaymentMethod.EFT_OUT, CONFIDENCE_SIGN_ONLY, "salary-phrase-outflow"
        if method is PaymentMethod.EFT_OUT and is_inflow:
            return PaymentMethod.EFT_IN, CONFIDENCE_PHRASE, "eft-phrase-inflow"
        if method is PaymentMethod.CASH_DEPOSIT and not is_inflow:
            return PaymentMethod.ATM_WITHDRAWAL, CONFIDENCE_PHRASE, "cash-phrase-outflow"
        return method, CONFIDENCE_PHRASE, pattern.pattern

    fallback = PaymentMethod.EFT_IN if is_inflow else PaymentMethod.EFT_OUT
    return fallback, CONFIDENCE_SIGN_ONLY, "direction-only"


def classify_purpose(
    description: str, *, amount: Decimal, method: PaymentMethod
) -> tuple[SpendingPurpose, Decimal, str]:
    """Decide what the payment was for.

    Formula:
        1. The first matching rule in `_PURPOSE_RULES` wins, with that rule's confidence.
        2. Failing that, each description token is compared by `levenshtein_ratio` against
           the known-merchant vocabulary, and the best pair at or above
           FUZZY_MERCHANT_THRESHOLD wins with CONFIDENCE_FUZZY. This is the step that
           recognises "WOOLWORTS CLAREMNT" as groceries.
        3. Failing that, the method and the sign decide as much as they can: an inflow is
           other income, a bank-fee method is bank charges, an internal transfer is a
           transfer, and anything else is UNKNOWN.

    Assumptions:
        - A rule match that contradicts the sign is dropped rather than trusted. "SALARY"
          on an outflow is not income, and classifying it as income would inflate the
          month's income and the savings rate derived from it — the precise corruption
          specs/transactions.md step 4 exists to prevent.
        - UNKNOWN is a real answer and is returned rather than a low-confidence guess. A
          wrong purpose silently moves a figure the user will act on; an unknown one shows
          up as uncategorised and gets reviewed.

    Rounding:
        Confidence is one of the module's fixed six-place constants.

    Raises:
        Nothing.
    """
    is_inflow = amount > 0

    for pattern, purpose, confidence in _PURPOSE_RULES:
        if not pattern.search(description):
            continue
        kind = PURPOSE_KIND[purpose]
        if kind is SpendKind.INCOME and not is_inflow:
            continue
        if kind is not SpendKind.INCOME and is_inflow and purpose is not SpendingPurpose.SAVINGS:
            # An inflow described as an expense is a refund of that expense, not the
            # expense itself. Left to the income rules below rather than booked as
            # negative spending, which no cash-flow figure in this system models.
            continue
        return purpose, confidence, pattern.pattern

    best_purpose: SpendingPurpose | None = None
    best_ratio = Decimal("0")
    best_token = ""
    for token in tokenise(description):
        if len(token) < _MIN_FUZZY_TOKEN_LENGTH or token in _MECHANICAL_TOKENS:
            continue
        for known, purpose in _FUZZY_MERCHANT_TOKENS:
            ratio = levenshtein_ratio(token, known)
            if ratio > best_ratio:
                best_purpose, best_ratio, best_token = purpose, ratio, known
    if best_purpose is not None and best_ratio >= FUZZY_MERCHANT_THRESHOLD:
        kind = PURPOSE_KIND[best_purpose]
        if (kind is SpendKind.INCOME) == is_inflow:
            return best_purpose, CONFIDENCE_FUZZY, f"fuzzy:{best_token}"

    if method is PaymentMethod.INTERNAL_TRANSFER:
        return SpendingPurpose.INTERNAL_TRANSFER, CONFIDENCE_MERCHANT, "method:internal_transfer"
    if method is PaymentMethod.BANK_FEE:
        return SpendingPurpose.BANK_CHARGES, CONFIDENCE_MERCHANT, "method:bank_fee"
    if method is PaymentMethod.SALARY_DEPOSIT:
        return SpendingPurpose.SALARY, CONFIDENCE_MERCHANT, "method:salary_deposit"
    if method is PaymentMethod.INTEREST:
        purpose = SpendingPurpose.OTHER_INCOME if is_inflow else SpendingPurpose.DEBT_REPAYMENT
        return purpose, CONFIDENCE_MERCHANT, "method:interest"
    if is_inflow:
        return SpendingPurpose.OTHER_INCOME, CONFIDENCE_SIGN_ONLY, "direction-only"

    return SpendingPurpose.UNKNOWN, CONFIDENCE_NONE, "none"


def classify_payment(*, description: str, amount: Decimal) -> PaymentClassification:
    """Classify one statement line into a payment method and a spending purpose.

    Formula:
        `classify_method` then `classify_purpose`, which is given the method because some
        purposes are only decidable from it (a bank fee has no merchant to recognise). The
        kind is `PURPOSE_KIND[purpose]`, or None when the purpose is UNKNOWN — an unknown
        purpose has no cash-flow effect this engine is willing to assert.

    Assumptions:
        - `description` is the original statement text or its normalised form; both work,
          and the normalised form matches slightly better because reference numbers are
          already gone.
        - Deterministic and history-free. Two users with the same description and amount
          get the same classification, which is what makes the result explainable and
          testable. Personalisation happens one layer up, in CategorisationService.

    Rounding:
        Confidences are fixed six-place constants.

    Raises:
        Nothing. Every input classifies, possibly as UNKNOWN.
    """
    method, method_confidence, method_rule = classify_method(description, amount=amount)
    purpose, purpose_confidence, purpose_rule = classify_purpose(
        description, amount=amount, method=method
    )
    kind = PURPOSE_KIND.get(purpose)

    return PaymentClassification(
        method=method,
        purpose=purpose,
        kind=kind,
        merchant=extract_merchant(description),
        method_confidence=method_confidence,
        purpose_confidence=purpose_confidence,
        matched_rule=f"{method_rule} | {purpose_rule}",
    )
