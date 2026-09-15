from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


class DomainError(Exception):
    """Base for exceptions services raise. Maps to the single error envelope in docs/api.md.

    Route handlers never catch these to translate them — the app-wide error handler does.
    """

    code: str = "internal_error"
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404
    message = "No resource with that identifier exists for this user."


class ValidationError(DomainError):
    code = "validation_error"
    status_code = 400
    message = "The request was not valid."


class SemanticError(DomainError):
    """422 — well-formed but not semantically valid, e.g. a negative principal."""

    code = "semantic_error"
    status_code = 422
    message = "The request could not be processed."


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409
    message = "The request conflicts with the resource's current state."


class UnauthenticatedError(DomainError):
    code = "unauthenticated"
    status_code = 401
    message = "Authentication is required."


class RateLimitedError(DomainError):
    code = "rate_limited"
    status_code = 429
    message = "Too many requests."


def _envelope(code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def _handle_domain_error(err: DomainError):
        return jsonify(_envelope(err.code, err.message, err.details)), err.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_error(err: HTTPException):
        return (
            jsonify(_envelope(err.name.lower().replace(" ", "_"), err.description or "", {})),
            err.code or 500,
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):
        app.logger.exception("unhandled exception")
        return jsonify(_envelope("internal_error", "An unexpected error occurred.", {})), 500
