from uuid import UUID

from flask import Blueprint, g, jsonify, request

from app.core.auth import require_auth
from app.core.errors import NotFoundError, ValidationError
from app.core.extensions import db
from app.repositories.import_batch import ImportBatchRepository
from app.services.financial_health import FinancialHealthService
from app.services.import_service import ImportService

bp = Blueprint("imports", __name__, url_prefix="/imports")


@bp.post("")
@require_auth
def create_import():
    if "file" not in request.files:
        raise ValidationError("A multipart 'file' field is required.")
    account_id = request.form.get("account_id")
    if not account_id:
        raise ValidationError("'account_id' is required.")

    # An explicit mapping is how a user gets past a format this build cannot detect;
    # it is remembered against the account, so it is supplied once, not every import.
    mapping = None
    if request.form.get("mapping"):
        import json

        from app.services.csv_formats import ColumnMapping

        try:
            mapping = ColumnMapping(**json.loads(request.form["mapping"]))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid column mapping: {exc}") from exc

    service = ImportService(db.session)
    summary = service.stage_csv(
        user_id=g.user_id,
        account_id=UUID(account_id),
        file_bytes=request.files["file"].read(),
        mapping=mapping,
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


@bp.get("/<uuid:batch_id>/conflicts")
@require_auth
def get_conflicts(batch_id):
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
    body = request.get_json(force=True, silent=True) or {}
    resolutions = {
        UUID(r["candidate_id"]): r["action"] for r in body.get("resolutions", [])
    }
    ImportService(db.session).resolve_conflicts(batch_id, user_id=g.user_id, resolutions=resolutions)
    return "", 204


@bp.post("/<uuid:batch_id>/commit")
@require_auth
def commit_import(batch_id):
    summary = ImportService(db.session).commit(batch_id, user_id=g.user_id)

    # "Computed ... on material change" per specs/financial-health.md — a committed
    # import is exactly that; recomputed inline since this slice has no task queue wired
    # to the API layer yet (workers/financial_health.py is the same call, for the
    # scheduled path).
    FinancialHealthService(db.session).assess(user_id=g.user_id)

    return jsonify(_summary_dict(summary)), 200


@bp.post("/<uuid:batch_id>/undo")
@require_auth
def undo_import(batch_id):
    removed = ImportService(db.session).undo(batch_id, user_id=g.user_id)
    return jsonify({"rows_removed": removed}), 200


def _summary_dict(summary) -> dict:
    return {
        "batch_id": str(summary.batch_id),
        "status": summary.status.value,
        "rows_parsed": summary.rows_parsed,
        "rows_imported": summary.rows_imported,
        "rows_skipped_duplicate": summary.rows_skipped_duplicate,
        "rows_pending_conflict": summary.rows_pending_conflict,
        "rows_merged": summary.rows_merged,
    }
