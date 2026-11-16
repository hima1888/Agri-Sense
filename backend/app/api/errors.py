"""One error shape for every failure: {"error": {"code", "message", "details"}}."""

import logging
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("agri_sense.api")


class ApiError(Exception):
    status_code = 400
    code = "bad_request"
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class UnprocessableError(ApiError):
    status_code = 422
    code = "invalid"


def error_json(
    status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


# Postgres SQLSTATE codes for integrity violations.
_FK_VIOLATION = "23503"
_UNIQUE_VIOLATION = "23505"
_CHECK_VIOLATION = "23514"
_NOT_NULL_VIOLATION = "23502"


def integrity_to_response(exc: IntegrityError) -> JSONResponse:
    """Translate DB constraint failures into precise client errors (never a 500, never raw SQL)."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    column = getattr(diag, "column_name", None)
    details = {"constraint": constraint} if constraint else ({"field": column} if column else None)

    if sqlstate == _UNIQUE_VIOLATION:
        return error_json(409, "duplicate", "A record with these values already exists.", details)
    if sqlstate == _FK_VIOLATION:
        message_detail = str(getattr(diag, "message_detail", "") or "")
        if "is still referenced" in message_detail:
            return error_json(409, "in_use", "This record is still referenced by other records.", details)
        return error_json(422, "invalid_reference", "A referenced record does not exist.", details)
    if sqlstate == _CHECK_VIOLATION:
        return error_json(422, "constraint_violation", "A value is outside its allowed range.", details)
    if sqlstate == _NOT_NULL_VIOLATION:
        return error_json(422, "missing_value", f"'{column}' cannot be null.", details)
    logger.exception("Unhandled integrity error")
    return error_json(409, "integrity_error", "The change conflicts with existing data.", details)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_json(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        return integrity_to_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return error_json(422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_json(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return error_json(500, "internal_error", "An unexpected error occurred.")
