"""日志配置。

使用统一、易读的控制台格式配置标准 ``logging`` 模块。所有模块都通过
:func:`get_logger` 获取日志记录器，从而保证配置被一致地应用。
"""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """使用项目统一的格式与级别初始化根日志。

    可多次安全调用；一旦处理器已附加，后续调用为空操作。
    """
    level = logging.DEBUG if settings.APP_DEBUG else logging.INFO

    root = logging.getLogger()
    # 避免在重载时（例如 uvicorn --reload）附加重复的处理器。
    if not any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        root.addHandler(handler)
    root.setLevel(level)

    # 在开发环境下降低第三方库的日志噪音。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """返回使用项目格式配置好的日志记录器。"""
    return logging.getLogger(name)
