"""鉴权 DTO（Phase 7 RBAC Step 2）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """登录 / refresh 后返回 access；refresh 走 HttpOnly cookie。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒
    user_id: int


class MeResponse(BaseModel):
    """GET /api/auth/me 返回当前登录态全貌（含 roles + permissions）。"""

    id: int
    username: str
    display_name: str
    is_super: bool
    roles: list[str]
    permissions: list[str]
    data_scope: str  # self / dept / all
    last_login_at: datetime | None = None
