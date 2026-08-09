"""认证相关 HTTP 路由：注册、登录、刷新和登出。

除 ``/auth/logout`` 外，所有认证端点都是公开的。``/auth/logout`` 需要
已认证用户，以便知道调用者是谁（尽管登出本身在服务端是无状态的）。
"""

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ResponseModel, success
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import login, refresh_token, register

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ResponseModel[LoginResponse])
async def register_endpoint(data: RegisterRequest, db: DbSession) -> dict:
    """注册新账号，并返回令牌及创建的用户。"""
    result = await register(db, data)
    return success(result)


@router.post("/login", response_model=ResponseModel[LoginResponse])
async def login_endpoint(data: LoginRequest, db: DbSession) -> dict:
    """使用邮箱和密码进行认证，返回令牌及用户信息。"""
    result = await login(db, data)
    return success(result)


@router.post("/refresh", response_model=ResponseModel[TokenResponse])
async def refresh_endpoint(data: RefreshRequest, db: DbSession) -> dict:
    """用刷新令牌换取新的访问令牌。"""
    result = await refresh_token(db, data)
    return success(result)


@router.post("/logout", response_model=ResponseModel[Any])
async def logout_endpoint(current_user: CurrentUser) -> dict:
    """无状态登出。

    服务端不保存会话状态，因此登出是一个空操作：客户端只需丢弃自己的
    访问令牌和刷新令牌。``current_user`` 依赖仍然必需，以确保只有已
    认证的调用者才能访问此端点。
    """
    # current_user 由依赖解析；登出本身是无状态的。
    _ = current_user
    return success(None)
