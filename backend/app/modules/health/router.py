"""health 模块的路由。

本模块是*垂直模块化*布局的规范模板：每个功能都拥有自己的路由、schemas
以及（后续的）服务/模型。路由由顶层 ``app/api/router.py`` 挂载在
``/api/v1`` 下。
"""

from fastapi import APIRouter

from app import __version__
from app.core.response import ResponseModel, success
from app.modules.health.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ResponseModel[HealthResponse], summary="Health check")
async def health_check() -> dict:
    """返回包裹在响应信封中的服务健康状态。

    Returns:
        ``{"code": 0, "message": "success", "data": {"status": "ok", ...}}``
    """
    data = HealthResponse(status="ok", version=__version__)
    return success(data=data)
