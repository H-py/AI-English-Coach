"""自定义异常与全局异常处理器。

每一条逃逸出路由的异常都会被这里转换为统一的响应信封
``{"code": <非零>, "message": ..., "data": null}``，使客户端始终收到
一致、机器可读的错误结构。
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.response import error

logger = get_logger(__name__)

# ---- 错误码约定 -------------------------------------------------------------
# 1xxxx -> 校验错误
# 2xxxx -> 认证 / 授权错误
# 5xxxx -> 服务器错误
# 9xxxx -> 通用业务错误
CODE_BUSINESS_ERROR = 90000
CODE_VALIDATION_ERROR = 10000
CODE_AUTH_ERROR = 20000
CODE_HTTP_ERROR = 40000
CODE_SERVER_ERROR = 50000


class BizException(Exception):
    """业务级异常。

    任何模块都可以抛出该异常来表示一个可恢复的、面向客户端的错误。
    全局处理器会捕获它并以给定的 ``code`` 和 ``message`` 作为信封返回。

    默认情况下 HTTP 状态码为 ``200``，使响应体成为客户端的唯一可信来源。
    对于必须触发 HTTP 级别语义的认证错误（例如让前端 axios 的 401 拦截器
    生效），请传入 ``http_status=401``。
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
    """在 FastAPI 应用上注册所有全局异常处理器。"""

    @app.exception_handler(BizException)
    async def _handle_biz_exception(_: Request, exc: BizException) -> JSONResponse:
        """处理自定义 :class:`BizException` 实例。

        HTTP 状态码取自 ``exc.http_status``（默认 200），使响应体（信封）
        成为唯一可信来源，同时仍允许在需要时让认证错误返回 401。
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
        """处理请求体校验失败（422）。"""
        logger.warning("Validation error: %s", exc.errors())
        return JSONResponse(
            status_code=200,
            content=error(
                CODE_VALIDATION_ERROR,
                "请求参数错误",
                data=detail(errors=exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """处理 Starlette/FastAPI 的 ``HTTPException`` 实例。

        ``fastapi.HTTPException`` 继承自 ``StarletteHTTPException``，因此
        一个处理器即可覆盖两者。
        """
        logger.warning("HTTPException: status=%s detail=%s", exc.status_code, exc.detail)
        return JSONResponse(
            status_code=200,
            content=error(CODE_HTTP_ERROR, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        """兜底处理器，将任何未预期的异常转换为统一响应。"""
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=200,
            content=error(CODE_SERVER_ERROR, "服务器内部错误，请稍后重试"),
        )


def detail(**kwargs: Any) -> dict:
    """辅助函数，用于构建错误响应的结构化 ``data`` 负载。"""
    return dict(kwargs)
