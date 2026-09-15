from app.domain.debt_payoff import MultiDebtResult, StrategyComparison, WhatIfResult
from app.models.debt import Debt


def debt_dict(debt: Debt) -> dict:
    return {
        "id": str(debt.id),
        "account_id": str(debt.account_id) if debt.account_id else None,
        "debt_type": debt.debt_type.value,
        "original_principal": str(debt.original_principal),
        "current_balance": str(debt.current_balance),
        "annual_rate": str(debt.annual_rate),
        "minimum_payment": str(debt.minimum_payment),
        "instalment": str(debt.instalment) if debt.instalment is not None else None,
        "term_months": debt.term_months,
        "started_on": debt.started_on.isoformat(),
    }


def schedule_period_dict(period) -> dict:
    return {
        "period": period.period,
        "opening_balance": str(period.opening_balance),
        "instalment": str(period.instalment),
        "interest": str(period.interest),
        "principal": str(period.principal),
        "closing_balance": str(period.closing_balance),
    }


def what_if_dict(result: WhatIfResult) -> dict:
    return {
        "extra_monthly": str(result.extra_monthly),
        "months_to_free": result.months_to_free,
        "total_interest": str(result.total_interest),
        "months_saved": result.months_saved,
        "interest_saved": str(result.interest_saved),
    }


def multi_debt_result_dict(result: MultiDebtResult) -> dict:
    return {
        "strategy": result.strategy,
        "months_to_free": result.months_to_free,
        "total_interest": str(result.total_interest),
        "payoff_month_by_debt_id": dict(result.payoff_month_by_debt_id),
        "schedule": [
            {
                "month": p.month,
                "total_balance": str(p.total_balance),
                "interest": str(p.interest),
                "principal": str(p.principal),
                "payment": str(p.payment),
            }
            for p in result.schedule
        ],
    }


def strategy_comparison_dict(comparison: StrategyComparison) -> dict:
    return {
        "avalanche": multi_debt_result_dict(comparison.avalanche),
        "snowball": multi_debt_result_dict(comparison.snowball),
        "consolidation": (
            multi_debt_result_dict(comparison.consolidation)
            if comparison.consolidation is not None
            else None
        ),
        "interest_difference_avalanche_vs_snowball": str(
            comparison.interest_difference_avalanche_vs_snowball
        ),
        "months_difference_avalanche_vs_snowball": comparison.months_difference_avalanche_vs_snowball,
        "difference_is_material": comparison.difference_is_material,
    }
