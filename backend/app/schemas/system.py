"""系统管理 DTO（Phase 7 v0.7.2：用户 / 角色 / 权限管理）。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataScope = Literal["self", "dept", "all"]


# ── Permission ─────────────────────────────────────────────────────


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    description: str


# ── Role ───────────────────────────────────────────────────────────


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    data_scope: DataScope
    description: str
    created_at: datetime
    updated_at: datetime


class RoleDetailOut(RoleOut):
    """角色详情：含其绑定的所有权限点 code。"""

    permission_codes: list[str]


class RoleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    data_scope: DataScope = "self"
    description: str = Field(default="", max_length=256)


class RoleUpdate(BaseModel):
    """部分更新：所有字段可选。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    data_scope: DataScope | None = None
    description: str | None = Field(default=None, max_length=256)


class RolePermissionAssign(BaseModel):
    """重设角色的权限点集合（全量覆盖，前端传完整列表）。"""

    permission_codes: list[str]


# ── User ───────────────────────────────────────────────────────────


class UserListItem(BaseModel):
    """列表项：精简字段，含角色 code 列表。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    email: str | None
    is_active: bool
    is_super: bool
    created_at: datetime
    last_login_at: datetime | None
    role_codes: list[str]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=128)
    email: str | None = Field(default=None, max_length=128)
    is_active: bool = True
    is_super: bool = False
    role_codes: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """更新基本资料；不含密码（独立端点）和 is_super（受限端点）。"""

    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class UserRolesAssign(BaseModel):
    """重设用户的角色集合（全量覆盖）。"""

    role_codes: list[str]


class PasswordReset(BaseModel):
    """admin 重置任意用户密码；不需要旧密码。"""

    new_password: str = Field(min_length=6, max_length=128)


class PasswordChange(BaseModel):
    """用户改自己的密码：必须验证旧密码。"""

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
