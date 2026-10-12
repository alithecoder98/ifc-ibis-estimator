"""Uniform error responses: every error body looks like {"error": {"code", "message"}}.

Registered on the app in app/main.py via `register_error_handlers(app)`.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Register on Starlette's base HTTPException, not fastapi.exceptions.HTTPException —
# in this FastAPI version the latter is a *subclass*, and routing-level errors (e.g. a
# path that matches no route) raise the Starlette base class directly. A handler
# registered on the subclass would miss those; registering on the base class catches
# both (isinstance covers FastAPI's own HTTPException too).
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            code=_status_to_code(exc.status_code), message=str(exc.detail)
        ),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(code="validation_error", message=str(exc.errors())),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            code="internal_error", message="An unexpected error occurred."
        ),
    )


def _status_to_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
    }.get(status_code, "http_error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
