from app.domain.goals import FundingPlan
from app.models.goal import Goal
from app.services.goal import GoalProgressView


def goal_dict(goal: Goal) -> dict:
    return {
        "id": str(goal.id),
        "name": goal.name,
        "account_id": str(goal.account_id) if goal.account_id else None,
        "target_amount": str(goal.target_amount),
        "target_date": goal.target_date.isoformat(),
        "priority": goal.priority,
        "planned_monthly_contribution": (
            str(goal.planned_monthly_contribution)
            if goal.planned_monthly_contribution is not None
            else None
        ),
    }


def progress_dict(view: GoalProgressView) -> dict:
    """The `GET /goals/{id}/progress` payload from docs/api.md.

    `is_achievable` false always arrives with `monthly_shortfall` and, where a date exists
    at all, `date_slippage_months` — per requirement 9, the gap is quantified rather than
    an indefinite progress figure being returned.
    """
    assessment = view.assessment
    return {
        "goal": goal_dict(view.goal),
        "current_amount": str(assessment.current_amount),
        "target_amount": str(assessment.target_amount),
        "progress_source": view.progress_source,
        "months_remaining": assessment.months_remaining,
        "required_monthly_contribution": str(assessment.required_monthly_contribution),
        "observed_monthly_rate": str(assessment.observed_monthly_rate),
        "projected_months": assessment.projected_months,
        "projected_achievement_date": (
            assessment.projected_achievement_date.isoformat()
            if assessment.projected_achievement_date
            else None
        ),
        "is_achievable": assessment.is_achievable,
        "monthly_shortfall": str(assessment.monthly_shortfall),
        "date_slippage_months": assessment.date_slippage_months,
        "annual_rate": str(view.annual_rate),
    }


def funding_plan_dict(plan: FundingPlan) -> dict:
    return {
        "total_required": str(plan.total_required),
        "available_cash_flow": str(plan.available_cash_flow),
        "is_over_committed": plan.is_over_committed,
        "fundings": [
            {
                "goal_id": f.key,
                "priority": f.priority,
                "required_monthly": str(f.required_monthly),
                "funded_monthly": str(f.funded_monthly),
                "is_fully_funded": f.is_fully_funded,
                "slippage_months": f.slippage_months,
            }
            for f in plan.fundings
        ],
    }
