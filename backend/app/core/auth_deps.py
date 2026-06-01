"""FastAPI 鉴权依赖（Phase 7 RBAC Step 2）。

提供：
- get_current_user：从 Authorization Bearer 解析 access token → User（含 roles+permissions）
- require_permission(code)：路由装饰用，权限不足直接 403
- CurrentUser：Annotated 类型别名，路由签名直接用

设计：
- super 用户（is_super=true）绕过所有权限检查
- selectinload 一次加载 roles 和 permissions，避免 N+1
- access token 命中黑名单视为失效（支持 logout 即时失效）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TOKEN_TYPE_ACCESS,
    TokenError,
    decode_token,
    is_jti_blacklisted,
)
from app.db.models.permission import Permission
from app.db.models.role import Role, RolePermission, UserRole
from app.db.models.user import User
from app.deps import DB


@dataclass
class AuthUser:
    """登录态视图：user 本体 + 扁平的 roles/permissions 集合 + data_scope。"""

    id: int
    username: str
    display_name: str
    is_super: bool
    role_codes: frozenset[str] = field(default_factory=frozenset)
    permission_codes: frozenset[str] = field(default_factory=frozenset)
    # 取所有角色中权限最宽的：all > dept > self
    data_scope: str = "self"

    def has_permission(self, code: str) -> bool:
        return self.is_super or code in self.permission_codes

    def has_any(self, *codes: str) -> bool:
        return self.is_super or any(c in self.permission_codes for c in codes)


_SCOPE_RANK = {"self": 0, "dept": 1, "all": 2}


def _widest_scope(scopes: list[str]) -> str:
    if not scopes:
        return "self"
    return max(scopes, key=lambda s: _SCOPE_RANK.get(s, -1))


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth[7:].strip()


async def load_auth_user(db: AsyncSession, user_id: int) -> AuthUser:
    """一次 SELECT 加载 user + roles + permissions。"""
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )

    # roles：selectin → role_permissions → permissions
    role_rows = (
        await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    role_codes = {r.code for r in role_rows}
    scopes = [r.data_scope for r in role_rows]
    role_ids = [r.id for r in role_rows]

    if role_ids:
        perm_rows = (
            await db.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id.in_(role_ids))
                .distinct()
            )
        ).scalars().all()
    else:
        perm_rows = []

    return AuthUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        is_super=bool(user.is_super),
        role_codes=frozenset(role_codes),
        permission_codes=frozenset(perm_rows),
        data_scope=_widest_scope(scopes),
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = DB,
) -> AuthUser:
    """解析 Bearer access token → AuthUser。失败抛 401。"""
    token = _bearer_token(request)
    try:
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    jti = payload.get("jti", "")
    if await is_jti_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token subject",
        ) from e

    return await load_auth_user(db, user_id)


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


def require_permission(*codes: str):
    """权限闸门：缺任一权限即 403（super 跳过）。

    用法：
        @router.get("/x", dependencies=[Depends(require_permission("strategy.read"))])
    """

    async def _checker(user: CurrentUser) -> AuthUser:
        if user.is_super:
            return user
        missing = [c for c in codes if c not in user.permission_codes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {','.join(missing)}",
            )
        return user

    return _checker


def require_any_permission(*codes: str):
    """权限闸门（任一即可）：所有 codes 都没有才 403。"""

    async def _checker(user: CurrentUser) -> AuthUser:
        if user.is_super or any(c in user.permission_codes for c in codes):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"need any of: {','.join(codes)}",
        )

    return _checker
