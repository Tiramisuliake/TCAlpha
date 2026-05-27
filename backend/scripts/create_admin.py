"""交互式创建 / 重置超级管理员（Phase 7 v0.7.0a）。

行为：
- 询问 username / password（不回显，两次确认）
- 用户已存在 → 更新 password_hash / is_super=true / is_active=true / display_name（如填）
- 用户不存在 → 新建
- 自动绑定 admin 角色（如未绑定）

用法（在 backend 目录）：
    uv run python scripts/create_admin.py
"""
from __future__ import annotations

import asyncio
import getpass
import sys

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

import app.db.postgres as pg  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models.role import Role, UserRole  # noqa: E402
from app.db.models.user import User  # noqa: E402


async def _ensure_admin(username: str, password: str, display_name: str) -> tuple[int, bool]:
    """返回 (user_id, created)。"""
    async with pg.async_session_factory() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        created = False
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name or username,
                is_active=True,
                is_super=True,
            )
            db.add(user)
            created = True
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            user.is_super = True
            if display_name:
                user.display_name = display_name
        await db.commit()
        await db.refresh(user)

        # 绑 admin 角色
        admin_role = (
            await db.execute(select(Role).where(Role.code == "admin"))
        ).scalar_one_or_none()
        if admin_role is None:
            print("⚠ 数据库未找到 admin 角色，跳过角色绑定（请先执行 alembic upgrade head）")
        else:
            exists = (
                await db.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == admin_role.id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(UserRole(user_id=user.id, role_id=admin_role.id))
                await db.commit()

        return user.id, created


def _prompt() -> tuple[str, str, str]:
    username = input("username (default=admin): ").strip() or "admin"
    display_name = input("display name (可选): ").strip()
    pwd = getpass.getpass("password (≥8 位): ")
    pwd2 = getpass.getpass("confirm  : ")
    if pwd != pwd2:
        print("✗ 两次输入不一致")
        sys.exit(1)
    if len(pwd) < 8:
        print("✗ 密码至少 8 位")
        sys.exit(1)
    return username, pwd, display_name


async def main() -> None:
    pg.init_engine()
    try:
        username, password, display_name = _prompt()
        user_id, created = await _ensure_admin(username, password, display_name)
        action = "created" if created else "updated"
        print(f"✓ admin {action}: id={user_id} username={username}")
    finally:
        await pg.dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
