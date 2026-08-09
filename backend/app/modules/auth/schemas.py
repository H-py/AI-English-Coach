"""auth 模块的 Pydantic schemas。

请求 schemas 描述了注册 / 登录 / 刷新的载荷，而响应 schemas
（:class:`TokenResponse`、:class:`LoginResponse`）定义了认证流程成功后
客户端收到的内容。
"""

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.schemas import UserOut


class RegisterRequest(BaseModel):
    """创建新账号的载荷。"""

    email: EmailStr
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """对已有账号进行认证的载荷。"""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """用刷新令牌换取新访问令牌的载荷。"""

    refresh_token: str


class TokenResponse(BaseModel):
    """刷新操作后返回的令牌对。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    """令牌对加上已认证用户，在注册/登录后返回。"""

    user: UserOut
