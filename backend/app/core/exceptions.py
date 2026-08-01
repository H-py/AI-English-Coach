"""Custom exceptions and global exception handlers.

Every exception that escapes a route is translated here into the unified
response envelope ``{"code": <non-zero>, "message": ..., "data": null}`` so
that clients always receive a consistent, machine-readable error shape.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.response import error

logger = get_logger(__name__)

# ---- Error code conventions -------------------------------------------------
# 1xxxx -> validation errors
# 2xxxx -> authentication / authorisation errors
# 5xxxx -> server errors
# 9xxxx -> generic business errors
CODE_BUSINESS_ERROR = 90000
CODE_VALIDATION_ERROR = 10000
CODE_AUTH_ERROR = 20000
CODE_HTTP_ERROR = 40000
CODE_SERVER_ERROR = 50000


class BizException(Exception):
    """Business-level exception.

    Raise this from any module to signal a recoverable, client-facing error.
    It is caught by the global handler and returned as an envelope with the
    given ``code`` and ``message``.

    By default the HTTP status code is ``200`` so the response body is the
    single source of truth for clients. For authentication errors that must
    trigger HTTP-level semantics (e.g. so that front-end axios 401 interceptors
    fire), pass ``http_status=401``.
    """

    def __init__(
        self,
        message: str = "business error",
        code: int = CODE_BUSINESS_ERROR,
        data: Any = None,
        http_status: int = 200,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.http_status = http_status


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(BizException)
    async def _handle_biz_exception(_: Request, exc: BizException) -> JSONResponse:
        """Handle custom :class:`BizException` instances.

        The HTTP status code is taken from ``exc.http_status`` (default 200)
        so that the response body (envelope) is the single source of truth,
        while still allowing auth errors to return 401 when needed.
        """
        logger.warning("BizException: code=%s message=%s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content=error(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request payload validation failures (422)."""
        logger.warning("Validation error: %s", exc.errors())
        return JSONResponse(
            status_code=200,
            content=error(
                CODE_VALIDATION_ERROR,
                "validation error",
                data=detail(errors=exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle Starlette/FastAPI ``HTTPException`` instances.

        ``fastapi.HTTPException`` subclasses ``StarletteHTTPException``, so a
        single handler covers both.
        """
        logger.warning("HTTPException: status=%s detail=%s", exc.status_code, exc.detail)
        return JSONResponse(
            status_code=200,
            content=error(CODE_HTTP_ERROR, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler that converts any unexpected exception."""
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=200,
            content=error(CODE_SERVER_ERROR, "internal server error"),
        )


def detail(**kwargs: Any) -> dict:
    """Helper to build a structured ``data`` payload for error responses."""
    return dict(kwargs)
