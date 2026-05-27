"""鉴权业务（Phase 7 RBAC Step 2）。

职责：
- 用户名 / 密码核对（统一错误，防用户名枚举）
- 更新 last_login_at
- 签发 access + refresh token 对（refresh 同时返回 jti / exp 供路由写 cookie）
- refresh 旋转：旧 jti 拉黑 → 发新对
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TOKEN_TYPE_REFRESH,
    TokenError,
    blacklist_jti,
    create_access_token,
    create_refresh_token,
    decode_token,
    is_jti_blacklisted,
    ttl_from_payload,
    verify_password,
)
from app.db.models.user import User


class AuthError(Exception):
    """登录 / refresh 业务错误（无效凭据 / 用户禁用 / refresh 过期）。"""


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    """核对用户名 + 密码，成功返回 User，否则 AuthError。"""
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("invalid credentials")
    if not verify_password(password, user.password_hash):
        raise AuthError("invalid credentials")
    return user


async def mark_login(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(last_login_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def issue_token_pair(user_id: int) -> tuple[str, str, str, datetime, int]:
    """签发 (access_token, refresh_token, refresh_jti, refresh_exp, access_ttl_seconds)。"""
    access_token, _access_jti, access_exp = create_access_token(user_id)
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(user_id)

    access_ttl = int(
        (access_exp - datetime.now(timezone.utc)).total_seconds()
    )
    return access_token, refresh_token, refresh_jti, refresh_exp, access_ttl


async def rotate_refresh(
    refresh_token: str,
) -> tuple[int, str, str, str, datetime, int]:
    """校验 refresh 并旋转：

    返回 (user_id, new_access, new_refresh, new_refresh_jti, new_refresh_exp, access_ttl)。
    旧 refresh jti 拉黑（防重放）。
    """
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except TokenError as e:
        raise AuthError(f"invalid refresh token: {e}") from e

    jti = payload["jti"]
    if await is_jti_blacklisted(jti):
        raise AuthError("refresh token revoked")

    user_id = int(payload["sub"])

    # 先签新 token，再把旧 jti 拉黑（顺序保证：失败不会留下死掉的旧 jti 状态）
    access_token, new_refresh, new_jti, new_exp, access_ttl = await issue_token_pair(
        user_id
    )

    await blacklist_jti(jti, ttl_from_payload(payload))
    return user_id, access_token, new_refresh, new_jti, new_exp, access_ttl


async def revoke_refresh(refresh_token: str) -> None:
    """logout：把 refresh jti 拉黑。已过期 / 解析失败也吞掉（幂等）。"""
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except TokenError:
        return
    await blacklist_jti(payload["jti"], ttl_from_payload(payload))


async def revoke_access(access_token: str) -> None:
    """logout 时如果带了 access，也顺手拉黑（即时失效，不等 15min）。"""
    from app.core.security import TOKEN_TYPE_ACCESS

    try:
        payload = decode_token(access_token, expected_type=TOKEN_TYPE_ACCESS)
    except TokenError:
        return
    await blacklist_jti(payload["jti"], ttl_from_payload(payload))
