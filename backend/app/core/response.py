"""统一的 API 响应信封。

每个端点都返回相同的 JSON 结构::

    {"code": 0, "message": "success", "data": {}}

``code`` 为 ``0`` 表示成功；任何非零值表示业务或系统错误。本模块提供
:class:`ResponseModel` Pydantic 模型以及便捷助手 :func:`success` 和
:func:`error`。
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """泛型响应信封模型。

    ``data`` 字段被参数化，使 OpenAPI 文档能够反映每个端点的具体负载
    类型，同时在线上仍保持单一、统一的响应结构。
    """

    model_config = ConfigDict(from_attributes=True)

    code: int = 0
    message: str = "success"
    data: Optional[T] = None


def success(data: Any = None, message: str = "success") -> dict:
    """构建成功响应字典（``code == 0``）。"""
    return {"code": 0, "message": message, "data": data}


def error(code: int, message: str, data: Any = None) -> dict:
    """构建错误响应字典（``code != 0``）。"""
    return {"code": code, "message": message, "data": data}
