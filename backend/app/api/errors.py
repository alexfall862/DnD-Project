"""Standard error envelope (api-contracts.md §2) and request ids (§24)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ApiError(Exception):
    status_code = 400
    code = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(ApiError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedPerspectiveError(ApiError):
    status_code = 403
    code = "UNAUTHORIZED_PERSPECTIVE"


class DebugModeRequired(ApiError):
    status_code = 403
    code = "DEBUG_MODE_REQUIRED"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def install(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )
