"""Wire shapes for spending detection and impact. See app/services/spending_insight.py.

Money and rates cross as strings (ADR-001), including the deltas — a delta is money and
rendering it as a JSON number would hand the client a float to round.
"""

from __future__ import annotations

from app.domain.spending_impact import MetricChange, SpendingImpact
from app.services.spending_insight import (
    AffectedArea,
    Commitment,
    DetectedRow,
    GroupTotal,
    SpendingInsight,
)


def metric_change_dict(change: MetricChange) -> dict:
    return {
        "name": change.name,
        "unit": change.unit,
        "before": str(change.before),
        "after": str(change.after),
        "delta": str(change.delta),
        "is_material": change.is_material,
    }


def impact_dict(impact: SpendingImpact) -> dict:
    return {
        "before": {
            "income": str(impact.before.income),
            "essential": str(impact.before.essential),
            "discretionary": str(impact.before.discretionary),
            "saving": str(impact.before.saving),
            "debt_service": str(impact.before.debt_service),
        },
        "after": {
            "income": str(impact.after.income),
            "essential": str(impact.after.essential),
            "discretionary": str(impact.after.discretionary),
            "saving": str(impact.after.saving),
            "debt_service": str(impact.after.debt_service),
        },
        "added": {
            "income": str(impact.added.income),
            "essential": str(impact.added.essential),
            "discretionary": str(impact.added.discretionary),
            "saving": str(impact.added.saving),
            "debt_service": str(impact.added.debt_service),
        },
        "changes": [metric_change_dict(change) for change in impact.changes],
    }


def detected_row_dict(row: DetectedRow) -> dict:
    return {
        "description": row.description,
        "merchant": row.merchant,
        "occurred_on": row.occurred_on.isoformat(),
        "amount": str(row.amount),
        "payment_method": row.payment_method.value,
        "spending_purpose": row.spending_purpose.value,
        "kind": row.kind.value if row.kind is not None else None,
        "purpose_confidence": str(row.purpose_confidence),
        "category_id": str(row.category_id) if row.category_id else None,
        "category_name": row.category_name,
        "category_basis": row.category_basis,
        "is_duplicate": row.is_duplicate,
        "needs_review": row.needs_review,
    }


def group_total_dict(total: GroupTotal) -> dict:
    return {
        "key": total.key,
        "label": total.label,
        "total": str(total.total),
        "monthly_average": str(total.monthly_average),
        "count": total.count,
    }


def commitment_dict(commitment: Commitment) -> dict:
    return {
        "label": commitment.label,
        "merchant": commitment.merchant,
        "method": commitment.method.value,
        "purpose": commitment.purpose.value,
        "monthly_amount": str(commitment.monthly_amount),
        "occurrences": commitment.occurrences,
        "is_new": commitment.is_new,
    }


def affected_dict(area: AffectedArea) -> dict:
    return {"area": area.area, "effect": area.effect, "detail": area.detail}


def insight_dict(insight: SpendingInsight) -> dict:
    return {
        "months_covered": insight.months_covered,
        "period_start": insight.period_start.isoformat() if insight.period_start else None,
        "period_end": insight.period_end.isoformat() if insight.period_end else None,
        "rows_needing_review": insight.rows_needing_review,
        "rows": [detected_row_dict(row) for row in insight.rows],
        "by_purpose": [group_total_dict(total) for total in insight.by_purpose],
        "by_method": [group_total_dict(total) for total in insight.by_method],
        "commitments": [commitment_dict(c) for c in insight.commitments],
        "impact": impact_dict(insight.impact),
        "affected": [affected_dict(area) for area in insight.affected],
    }
