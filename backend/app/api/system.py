"""系统管理路由（Phase 7 v0.7.2）。

三组 endpoint：
- /api/system/users        — system.user.read / system.user.write
- /api/system/roles        — system.role.read / system.role.write
- /api/system/permissions  — system.role.read（权限点是配角色时用，归入 role.read）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth_deps import CurrentUser, require_permission
from app.deps import DB
from app.schemas.system import (
    PasswordReset,
    PermissionOut,
    RoleCreate,
    RoleDetailOut,
    RoleOut,
    RolePermissionAssign,
    RoleUpdate,
    UserCreate,
    UserListItem,
    UserRolesAssign,
    UserUpdate,
)
from app.services import system as system_svc
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _to_user_item(user, role_codes: list[str]) -> UserListItem:
    return UserListItem(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        email=user.email,
        is_active=user.is_active,
        is_super=user.is_super,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        role_codes=role_codes,
    )


# ── /users ─────────────────────────────────────────────────────────


@router.get(
    "/users",
    response_model=list[UserListItem],
    dependencies=[Depends(require_permission("system.user.read"))],
)
async def list_users(db: AsyncSession = DB):
    rows = await system_svc.list_users(db)
    return [_to_user_item(u, codes) for u, codes in rows]


@router.post(
    "/users",
    response_model=UserListItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system.user.write"))],
)
async def create_user(payload: UserCreate, db: AsyncSession = DB):
    try:
        user = await system_svc.create_user(
            db,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            email=payload.email,
            is_active=payload.is_active,
            is_super=payload.is_super,
            role_codes=payload.role_codes,
        )
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    roles = await system_svc.get_user_roles(db, user.id)
    return _to_user_item(user, roles)


@router.put(
    "/users/{user_id}",
    response_model=UserListItem,
    dependencies=[Depends(require_permission("system.user.write"))],
)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: CurrentUser,
    db: AsyncSession = DB,
):
    try:
        user = await system_svc.update_user(
            db,
            user_id,
            display_name=payload.display_name,
            email=payload.email,
            is_active=payload.is_active,
            actor_id=actor.id,
        )
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    roles = await system_svc.get_user_roles(db, user.id)
    return _to_user_item(user, roles)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("system.user.write"))],
)
async def delete_user(user_id: int, actor: CurrentUser, db: AsyncSession = DB):
    try:
        ok = await system_svc.delete_user(db, user_id, actor_id=actor.id)
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")


@router.put(
    "/users/{user_id}/roles",
    response_model=UserListItem,
    dependencies=[Depends(require_permission("system.user.write"))],
)
async def set_user_roles(
    user_id: int,
    payload: UserRolesAssign,
    actor: CurrentUser,
    db: AsyncSession = DB,
):
    try:
        ok = await system_svc.set_user_roles(
            db, user_id, payload.role_codes, actor_id=actor.id
        )
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    user = await system_svc.get_user(db, user_id)
    roles = await system_svc.get_user_roles(db, user_id)
    return _to_user_item(user, roles)


@router.put(
    "/users/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("system.user.write"))],
)
async def reset_password(
    user_id: int, payload: PasswordReset, db: AsyncSession = DB
):
    ok = await system_svc.reset_password(db, user_id, payload.new_password)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")


# ── /roles ─────────────────────────────────────────────────────────


@router.get(
    "/roles",
    response_model=list[RoleOut],
    dependencies=[Depends(require_permission("system.role.read"))],
)
async def list_roles(db: AsyncSession = DB):
    return await system_svc.list_roles(db)


@router.get(
    "/roles/{role_id}",
    response_model=RoleDetailOut,
    dependencies=[Depends(require_permission("system.role.read"))],
)
async def get_role(role_id: int, db: AsyncSession = DB):
    role = await system_svc.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    codes = await system_svc.get_role_permission_codes(db, role_id)
    return RoleDetailOut(
        id=role.id,
        code=role.code,
        name=role.name,
        data_scope=role.data_scope,
        description=role.description,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permission_codes=codes,
    )


@router.post(
    "/roles",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system.role.write"))],
)
async def create_role(payload: RoleCreate, db: AsyncSession = DB):
    try:
        return await system_svc.create_role(
            db,
            code=payload.code,
            name=payload.name,
            data_scope=payload.data_scope,
            description=payload.description,
        )
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.put(
    "/roles/{role_id}",
    response_model=RoleOut,
    dependencies=[Depends(require_permission("system.role.write"))],
)
async def update_role(role_id: int, payload: RoleUpdate, db: AsyncSession = DB):
    role = await system_svc.update_role(
        db,
        role_id,
        name=payload.name,
        data_scope=payload.data_scope,
        description=payload.description,
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    return role


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("system.role.write"))],
)
async def delete_role(role_id: int, db: AsyncSession = DB):
    try:
        ok = await system_svc.delete_role(db, role_id)
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")


@router.put(
    "/roles/{role_id}/permissions",
    response_model=RoleDetailOut,
    dependencies=[Depends(require_permission("system.role.write"))],
)
async def set_role_permissions(
    role_id: int, payload: RolePermissionAssign, db: AsyncSession = DB
):
    try:
        ok = await system_svc.set_role_permissions(
            db, role_id, payload.permission_codes
        )
    except system_svc.SystemError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")

    role = await system_svc.get_role(db, role_id)
    codes = await system_svc.get_role_permission_codes(db, role_id)
    return RoleDetailOut(
        id=role.id,
        code=role.code,
        name=role.name,
        data_scope=role.data_scope,
        description=role.description,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permission_codes=codes,
    )


# ── /permissions ───────────────────────────────────────────────────


@router.get(
    "/permissions",
    response_model=list[PermissionOut],
    dependencies=[Depends(require_permission("system.role.read"))],
)
async def list_permissions(db: AsyncSession = DB):
    return await system_svc.list_permissions(db)
