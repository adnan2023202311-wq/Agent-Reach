"""
API layer: maps every error this API can produce to one JSON envelope.

Layer: Interface/Presentation.

The envelope shape — {"message": str, "code"?: str, "details"?: any} —
is not something this backend invented. It's the `ApiErrorBody`
contract already defined in the Lovable frontend's
`src/lib/api/types.ts`, written before this backend had any error
handling at all. This file makes the backend conform to that contract,
rather than the other way around, since the frontend's `api` client
(`src/lib/api/client.ts`) already parses responses assuming this shape
and would otherwise show "undefined" for every error message.

Three error sources exist, all normalized to the same envelope:
1. AgentReachError (our own domain exceptions) — status code chosen
   per exception type, as before.
2. HTTPException (raised directly by routes, e.g. the 501s in
   agents.py/tools.py/providers.py for unsupported mutations).
3. RequestValidationError (Pydantic request-body validation, e.g. an
   empty `message` field) — FastAPI's default shape for this
   ({"detail": [...]}) doesn't match the frontend's contract either.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from domain.exceptions import (
    AgentExecutionError,
    AgentNotRegisteredError,
    AgentReachError,
    ModelProviderError,
    PlanningError,
)

logger = logging.getLogger(__name__)

_STATUS_BY_EXCEPTION_TYPE: dict[type[AgentReachError], int] = {
    AgentNotRegisteredError: 500,  # a configuration bug, not the caller's fault
    PlanningError: 422,  # the request itself couldn't be decomposed
    AgentExecutionError: 502,  # an upstream agent/tool failed after retries
    ModelProviderError: 502,  # an upstream model provider failed (same category)
}
_DEFAULT_STATUS = 500


def _envelope(message: str, code: str | None = None, details: object | None = None) -> dict:
    return {"message": message, "code": code, "details": details}


async def _agent_reach_error_handler(request: Request, exc: AgentReachError) -> JSONResponse:
    status_code = _STATUS_BY_EXCEPTION_TYPE.get(type(exc), _DEFAULT_STATUS)
    logger.error("domain error handling %s: %s", request.url.path, exc, exc_info=exc)
    return JSONResponse(status_code=status_code, content=_envelope(str(exc), type(exc).__name__))


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # exc.detail is either a plain string (the common case) or a dict
    # a route passed explicitly to include a `code`, e.g.
    # HTTPException(501, detail={"message": "...", "code": "NOT_IMPLEMENTED"}).
    if isinstance(exc.detail, dict):
        body = _envelope(
            exc.detail.get("message", "Request failed"),
            exc.detail.get("code"),
            exc.detail.get("details"),
        )
    else:
        body = _envelope(str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=body)


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope("Invalid request", "VALIDATION_ERROR", exc.errors()),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for any exception not handled by more specific handlers.

    Logs the full traceback so the error is visible during development,
    then returns a generic 500 response. Without this handler, unhandled
    exceptions would produce a 500 with no logging, making debugging
    difficult.
    """
    logger.exception("Unhandled error handling %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content=_envelope("Internal server error", "INTERNAL_ERROR"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AgentReachError, _agent_reach_error_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
