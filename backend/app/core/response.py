"""Unified API response envelope.

Every endpoint returns the same JSON structure::

    {"code": 0, "message": "success", "data": {}}

``code`` equal to ``0`` indicates success; any non-zero value indicates a
business or system error. This module provides the :class:`ResponseModel`
Pydantic schema plus convenience helpers :func:`success` and :func:`error`.
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """Generic response envelope model.

    The ``data`` field is parametrised so that OpenAPI docs can reflect the
    concrete payload type of each endpoint while still keeping a single,
    uniform shape on the wire.
    """

    model_config = ConfigDict(from_attributes=True)

    code: int = 0
    message: str = "success"
    data: Optional[T] = None


def success(data: Any = None, message: str = "success") -> dict:
    """Build a success response dict (``code == 0``)."""
    return {"code": 0, "message": message, "data": data}


def error(code: int, message: str, data: Any = None) -> dict:
    """Build an error response dict (``code != 0``)."""
    return {"code": code, "message": message, "data": data}
