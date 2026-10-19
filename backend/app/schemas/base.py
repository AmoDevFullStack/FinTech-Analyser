"""Pydantic at the request boundary. See docs/api.md and docs/architecture.md.

Before this module, every route parsed its own query string and body by hand:
`Decimal(str(args["min_amount"]))`, `date.fromisoformat(args["from"])`, a loop over a
tuple of required field names. That has three problems this replaces.

  1. A malformed value raised whatever the coercion happened to raise — `ValueError`,
     `InvalidOperation`, `KeyError` — and reached the client as a 500 through the
     catch-all handler, instead of the 400 with a field name that docs/api.md promises.
  2. The accepted shape of a request lived only in the route body, so it could not be read
     without reading the parsing code, and no two routes spelled the same filter the same
     way.
  3. Nothing enforced bounds. `limit` was `int(args.get("limit", 50))`, which cheerfully
     accepted `limit=10000000` and turned one request into a full table scan.

A model here is the contract. `parse_query` and `parse_body` turn a pydantic
`ValidationError` into the project's own `ValidationError`, so the single error envelope in
docs/api.md is what the client sees, with `details.fields` naming exactly what was wrong.

Money stays a string across the wire per ADR-001, and the models below accept
`Decimal`-from-string rather than float. `strict` is deliberately off for query strings —
every query parameter arrives as text and coercing "50" to an int is the entire job — but
`extra="forbid"` is on, so a misspelled filter is an error rather than a filter silently
not applied.
"""

from __future__ import annotations

from typing import Any, TypeVar

from flask import request
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError

TModel = TypeVar("TModel", bound="ApiModel")


class ApiModel(BaseModel):
    """Base for every request model. Unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
        frozen=True,
    )


def _field_errors(exc: PydanticValidationError) -> dict[str, str]:
    """Flatten pydantic's error list into `{field: message}` for the error envelope.

    Only the first error per field is kept. A client fixing a field does not need the
    three separate reasons a union failed to match, and the full list is noise in a
    message a user might see.
    """
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "__root__"
        fields.setdefault(location, error["msg"])
    return fields


def _validate(model: type[TModel], payload: dict[str, Any], *, source: str) -> TModel:
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        fields = _field_errors(exc)
        summary = ", ".join(f"{name} ({reason})" for name, reason in fields.items())
        raise ValidationError(
            f"The request {source} was not valid: {summary}.",
            details={"fields": fields},
        ) from exc


def parse_query(model: type[TModel]) -> TModel:
    """Validate `request.args` against `model`.

    Repeated parameters collapse to the last value, matching what `request.args.get` did
    before — except for fields the model declares as a list, which take every value. That
    is how `?status=active&status=dismissed` works without a comma-separated-string
    convention the client has to know about.
    """
    payload: dict[str, Any] = {}
    list_fields = {
        name
        for name, field in model.model_fields.items()
        if _is_sequence_field(field.annotation)
    }
    aliases = {
        (field.alias or name): name for name, field in model.model_fields.items()
    }

    for key in request.args:
        target = aliases.get(key, key)
        if target in list_fields:
            payload[key] = request.args.getlist(key)
        else:
            payload[key] = request.args.get(key)

    return _validate(model, payload, source="query string")


def parse_body(model: type[TModel]) -> TModel:
    """Validate the JSON body against `model`.

    A missing or unparseable body validates as `{}`, so a model whose fields are all
    optional accepts an empty POST, and one with required fields reports them by name
    rather than complaining about the body as a whole.
    """
    body = request.get_json(force=True, silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise ValidationError("The request body must be a JSON object.")
    return _validate(model, body, source="body")


def parse_form(model: type[TModel]) -> TModel:
    """Validate `request.form` against `model`, for the multipart upload endpoints."""
    return _validate(model, dict(request.form), source="form")


def _is_sequence_field(annotation: Any) -> bool:
    origin = getattr(annotation, "__origin__", None)
    if origin in (list, tuple, set, frozenset):
        return True
    # `list[str] | None` arrives as a union; check its members.
    args = getattr(annotation, "__args__", ())
    return any(getattr(arg, "__origin__", None) in (list, tuple, set, frozenset) for arg in args)
