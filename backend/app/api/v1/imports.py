import json

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError, ValidationError
from app.core.extensions import db
from app.repositories.import_batch import ImportBatchRepository
from app.schemas.base import parse_body, parse_form
from app.schemas.insight import insight_dict
from app.schemas.requests import ColumnMappingRequest, ImportForm, ResolveImportRequest
from app.services.csv_formats import ColumnMapping
from app.services.import_service import ImportService
from app.services.spending_insight import SpendingInsightService

bp = Blueprint("imports", __name__, url_prefix="/imports")


@bp.post("")
@require_auth
def create_import():
    if "file" not in request.files:
        raise ValidationError("A multipart 'file' field is required.")
    form = parse_form(ImportForm)

    # An explicit mapping is how a user gets past a format this build cannot detect;
    # it is remembered against the account, so it is supplied once, not every import.
    mapping = None
    if form.mapping:
        try:
            raw = json.loads(form.mapping)
        except ValueError as exc:
            raise ValidationError(f"'mapping' is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValidationError("'mapping' must be a JSON object.")
        validated = ColumnMappingRequest.model_validate(raw)
        mapping = ColumnMapping(**validated.model_dump())

    # `stage_file`, not `stage_csv`: a statement arrives as a PDF at least as often as a
    # CSV, and which reader it needs is decided from the file's own bytes.
    summary = ImportService(db.session).stage_file(
        user_id=g.user_id,
        account_id=form.account_id,
        file_bytes=request.files["file"].read(),
        mapping=mapping,
        password=form.password,
    )
    return jsonify(_summary_dict(summary)), 202


@bp.get("/<uuid:batch_id>")
@require_auth
def get_import(batch_id):
    batch = ImportBatchRepository(db.session).get_for_user(batch_id, user_id=g.user_id)
    if batch is None:
        raise NotFoundError("No import batch with that identifier exists for this user.")
    return (
        jsonify(
            {
                "batch_id": str(batch.id),
                "status": batch.status.value,
                "detected_format": batch.detected_format,
                "rows_parsed": batch.rows_parsed,
                "rows_imported": batch.rows_imported,
                "rows_skipped_duplicate": batch.rows_skipped_duplicate,
                "rows_pending_conflict": batch.rows_pending_conflict,
                "rows_merged": batch.rows_merged,
            }
        ),
        200,
    )


@bp.get("/<uuid:batch_id>/preview")
@require_auth
def preview_import(batch_id):
    """What this staged file contains, and what committing it would change.

    The question a user actually has in front of an import is not "how many rows parsed"
    but "what is this going to do to my month". This endpoint answers that before anything
    is written: every row read with its payment type and purpose, the totals by each, the
    standing commitments the file introduces, and the before/after on cash flow, savings
    rate, debt-to-income and emergency-fund cover.
    """
    insight = SpendingInsightService(db.session).preview_batch(batch_id, user_id=g.user_id)
    return jsonify(insight_dict(insight)), 200


@bp.get("/<uuid:batch_id>/conflicts")
@require_auth
def get_conflicts(batch_id):
    batch = ImportBatchRepository(db.session).get_for_user(batch_id, user_id=g.user_id)
    if batch is None:
        raise NotFoundError("No import batch with that identifier exists for this user.")

    staged = ImportBatchRepository(db.session).staged_for(batch_id)
    conflicts = [s for s in staged if s.conflict_candidate_id is not None and s.resolution is None]
    return (
        jsonify(
            {
                "data": [
                    {
                        "candidate_id": str(c.id),
                        "occurred_on": c.occurred_on.isoformat(),
                        "amount": str(c.amount),
                        "description": c.description,
                        "existing_transaction_id": str(c.conflict_candidate_id),
                        "payment_method": (
                            c.payment_method.value if c.payment_method else None
                        ),
                        "spending_purpose": (
                            c.spending_purpose.value if c.spending_purpose else None
                        ),
                        "merchant": c.merchant,
                    }
                    for c in conflicts
                ]
            }
        ),
        200,
    )


@bp.post("/<uuid:batch_id>/resolve")
@require_auth
def resolve_import(batch_id):
    body = parse_body(ResolveImportRequest)
    resolutions = {r.candidate_id: r.action for r in body.resolutions}
    ImportService(db.session).resolve_conflicts(
        batch_id, user_id=g.user_id, resolutions=resolutions
    )
    return "", 204


@bp.post("/<uuid:batch_id>/commit")
@require_auth
def commit_import(batch_id):
    # Everything a committed import recomputes is registered against the
    # `import.committed` event in app/services/event_handlers.py. The route used to call
    # the health assessment itself, which is how the import path and the manual-entry path
    # came to recompute different things.
    summary = ImportService(db.session).commit(batch_id, user_id=g.user_id)
    return jsonify(_summary_dict(summary)), 200


@bp.post("/<uuid:batch_id>/undo")
@require_auth
def undo_import(batch_id):
    removed = ImportService(db.session).undo(batch_id, user_id=g.user_id)
    return jsonify({"rows_removed": removed}), 200


def _summary_dict(summary) -> dict:
    payload = {
        "batch_id": str(summary.batch_id),
        "status": summary.status.value,
        "rows_parsed": summary.rows_parsed,
        "rows_imported": summary.rows_imported,
        "rows_skipped_duplicate": summary.rows_skipped_duplicate,
        "rows_pending_conflict": summary.rows_pending_conflict,
        "rows_merged": summary.rows_merged,
    }
    if summary.insight is not None:
        payload["insight"] = insight_dict(summary.insight)
    return payload
