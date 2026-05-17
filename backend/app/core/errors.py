from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    """Application-level error with stable code + http status."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None) -> None:
        super().__init__("NOT_FOUND", message, http_status=status.HTTP_404_NOT_FOUND, details=details)


class ForbiddenError(APIError):
    def __init__(self, message: str = "Forbidden", details: dict[str, Any] | None = None) -> None:
        super().__init__("FORBIDDEN", message, http_status=status.HTTP_403_FORBIDDEN, details=details)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "Unauthorized", details: dict[str, Any] | None = None) -> None:
        super().__init__("UNAUTHORIZED", message, http_status=status.HTTP_401_UNAUTHORIZED, details=details)


class DuplicateResourceError(APIError):
    def __init__(self, message: str = "Resource already exists", details: dict[str, Any] | None = None) -> None:
        super().__init__("DUPLICATE_RESOURCE", message, http_status=status.HTTP_409_CONFLICT, details=details)


class TopicLimitExceededError(APIError):
    def __init__(self) -> None:
        super().__init__(
            "TOPIC_LIMIT_EXCEEDED",
            "A user can create at most 5 topics.",
            http_status=status.HTTP_409_CONFLICT,
        )


class RateLimitedError(APIError):
    def __init__(self, message: str = "Rate limited") -> None:
        super().__init__("RATE_LIMITED", message, http_status=status.HTTP_429_TOO_MANY_REQUESTS)


class UpstreamError(APIError):
    def __init__(self, message: str = "Upstream service error", details: dict[str, Any] | None = None) -> None:
        super().__init__("UPSTREAM_ERROR", message, http_status=status.HTTP_502_BAD_GATEWAY, details=details)


def _build_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error_handler(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_build_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_build_payload(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "DUPLICATE_RESOURCE",
            429: "RATE_LIMITED",
        }
        code = code_map.get(exc.status_code, "INTERNAL_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_payload(code, message),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_build_payload("INTERNAL_ERROR", str(exc) or "Internal error"),
        )
