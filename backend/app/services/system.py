"""系统管理业务（Phase 7 v0.7.2：用户 / 角色 / 权限）。

职责：
- 用户 CRUD（含密码 hash、角色重置、激活停用）
- 角色 CRUD（含权限点全量替换）
- 权限点只读列表
- 防御策略：不能删自己、不能撤销自己的 super 标志、不能删 admin 角色
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.permission import Permission
from app.db.models.role import Role, RolePermission, UserRole
from app.db.models.user import User


class SystemError(Exception):
    """系统管理业务错误（重名 / 自删 / 找不到等）。"""


# ── Permission（只读）──────────────────────────────────────────────


async def list_permissions(db: AsyncSession) -> list[Permission]:
    stmt = select(Permission).order_by(Permission.category, Permission.code)
    return list((await db.execute(stmt)).scalars().all())


# ── Role ───────────────────────────────────────────────────────────


async def list_roles(db: AsyncSession) -> list[Role]:
    stmt = select(Role).order_by(Role.id)
    return list((await db.execute(stmt)).scalars().all())


async def get_role(db: AsyncSession, role_id: int) -> Role | None:
    return (
        await db.execute(select(Role).where(Role.id == role_id))
    ).scalar_one_or_none()


async def get_role_permission_codes(db: AsyncSession, role_id: int) -> list[str]:
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    )
    return list((await db.execute(stmt)).scalars().all())


async def create_role(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    data_scope: str,
    description: str,
) -> Role:
    existing = (
        await db.execute(select(Role).where(Role.code == code))
    ).scalar_one_or_none()
    if existing is not None:
        raise SystemError(f"role code already exists: {code}")
    role = Role(code=code, name=name, data_scope=data_scope, description=description)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


async def update_role(
    db: AsyncSession,
    role_id: int,
    *,
    name: str | None,
    data_scope: str | None,
    description: str | None,
) -> Role | None:
    role = await get_role(db, role_id)
    if role is None:
        return None
    if name is not None:
        role.name = name
    if data_scope is not None:
        role.data_scope = data_scope
    if description is not None:
        role.description = description
    await db.commit()
    await db.refresh(role)
    return role


async def delete_role(db: AsyncSession, role_id: int) -> bool:
    role = await get_role(db, role_id)
    if role is None:
        return False
    if role.code == "admin":
        raise SystemError("cannot delete the built-in 'admin' role")
    await db.execute(delete(Role).where(Role.id == role_id))
    await db.commit()
    return True


async def set_role_permissions(
    db: AsyncSession, role_id: int, permission_codes: list[str]
) -> bool:
    """全量替换角色的权限点。"""
    role = await get_role(db, role_id)
    if role is None:
        return False

    if permission_codes:
        rows = (
            await db.execute(
                select(Permission.id, Permission.code).where(
                    Permission.code.in_(permission_codes)
                )
            )
        ).all()
        found_codes = {r.code for r in rows}
        missing = [c for c in permission_codes if c not in found_codes]
        if missing:
            raise SystemError(f"unknown permission codes: {','.join(missing)}")
        perm_ids = [r.id for r in rows]
    else:
        perm_ids = []

    await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    db.add_all([RolePermission(role_id=role_id, permission_id=pid) for pid in perm_ids])
    await db.commit()
    return True


# ── User ───────────────────────────────────────────────────────────


async def list_users(db: AsyncSession) -> list[tuple[User, list[str]]]:
    """返回 [(user, [role_code, ...]), ...]，列表页一次性出全。"""
    users = list(
        (await db.execute(select(User).order_by(User.id))).scalars().all()
    )
    if not users:
        return []

    # 一次性拉所有 user_role + role.code，避免 N+1
    user_ids = [u.id for u in users]
    rows = (
        await db.execute(
            select(UserRole.user_id, Role.code)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
        )
    ).all()

    by_user: dict[int, list[str]] = {uid: [] for uid in user_ids}
    for uid, code in rows:
        by_user[uid].append(code)
    for uid in by_user:
        by_user[uid].sort()
    return [(u, by_user[u.id]) for u in users]


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()


async def _resolve_role_ids(db: AsyncSession, role_codes: list[str]) -> list[int]:
    if not role_codes:
        return []
    rows = (
        await db.execute(
            select(Role.id, Role.code).where(Role.code.in_(role_codes))
        )
    ).all()
    found = {r.code for r in rows}
    missing = [c for c in role_codes if c not in found]
    if missing:
        raise SystemError(f"unknown role codes: {','.join(missing)}")
    return [r.id for r in rows]


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
    email: str | None,
    is_active: bool,
    is_super: bool,
    role_codes: list[str],
) -> User:
    existing = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if existing is not None:
        raise SystemError(f"username already exists: {username}")

    role_ids = await _resolve_role_ids(db, role_codes)

    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name or username,
        email=email,
        is_active=is_active,
        is_super=is_super,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if role_ids:
        db.add_all([UserRole(user_id=user.id, role_id=rid) for rid in role_ids])
        await db.commit()
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    *,
    display_name: str | None,
    email: str | None,
    is_active: bool | None,
    actor_id: int,
) -> User | None:
    user = await get_user(db, user_id)
    if user is None:
        return None
    if user_id == actor_id and is_active is False:
        raise SystemError("cannot deactivate yourself")

    if display_name is not None:
        user.display_name = display_name
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int, *, actor_id: int) -> bool:
    if user_id == actor_id:
        raise SystemError("cannot delete yourself")
    user = await get_user(db, user_id)
    if user is None:
        return False
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return True


async def set_user_roles(
    db: AsyncSession,
    user_id: int,
    role_codes: list[str],
    *,
    actor_id: int,
) -> bool:
    """全量替换用户角色。"""
    user = await get_user(db, user_id)
    if user is None:
        return False
    role_ids = await _resolve_role_ids(db, role_codes)

    # 防自残：actor 不能把自己从 admin 角色里摘掉（否则下一次刷新就 403）
    if user_id == actor_id and "admin" not in role_codes and user.is_super is False:
        raise SystemError("cannot remove admin role from yourself")

    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    db.add_all([UserRole(user_id=user_id, role_id=rid) for rid in role_ids])
    await db.commit()
    return True


async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> bool:
    user = await get_user(db, user_id)
    if user is None:
        return False
    user.password_hash = hash_password(new_password)
    await db.commit()
    return True


async def get_user_roles(db: AsyncSession, user_id: int) -> list[str]:
    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.code)
    )
    return list((await db.execute(stmt)).scalars().all())
