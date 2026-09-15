from flask import Blueprint, g, jsonify

from app.core.auth import require_auth
from app.core.extensions import db
from app.repositories.category import CategoryRepository

bp = Blueprint("categories", __name__, url_prefix="/categories")


@bp.get("")
@require_auth
def list_categories():
    categories = CategoryRepository(db.session).list_for_user(user_id=g.user_id)
    return (
        jsonify(
            {
                "data": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "kind": c.kind.value,
                        "parent_id": str(c.parent_id) if c.parent_id else None,
                        "is_system": c.user_id is None,
                    }
                    for c in categories
                ]
            }
        ),
        200,
    )
