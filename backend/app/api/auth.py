"""鉴权路由（Phase 7 RBAC Step 2）。

端点：
- POST /api/auth/login    — 用户名 / 密码 → access(json) + refresh(httponly cookie)
- POST /api/auth/refresh  — 读 refresh cookie → 旋转新 refresh + 新 access
- POST /api/auth/logout   — 拉黑 refresh + access + 清 cookie
- GET  /api/auth/me       — 解析 Bearer access → 当前用户（含 roles + permissions）

Cookie 安全：HttpOnly + SameSite=Strict（默认）+ Secure（生产）；
Path=/api/auth → 业务接口不会带 refresh，进一步降 CSRF 面。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth_deps import CurrentUser
from app.deps import get_db
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.services import auth as auth_svc

router = APIRouter()


def _set_refresh_cookie(
    response: Response, token: str, expires: datetime
) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
        expires=expires,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_svc.authenticate(db, payload.username, payload.password)
    except auth_svc.AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    access_token, refresh_token, _jti, refresh_exp, access_ttl = (
        await auth_svc.issue_token_pair(user.id)
    )
    _set_refresh_cookie(response, refresh_token, refresh_exp)
    await auth_svc.mark_login(db, user.id)

    return TokenResponse(
        access_token=access_token,
        expires_in=access_ttl,
        user_id=user.id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response):
    cookie_token = request.cookies.get(settings.refresh_cookie_name, "")
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing refresh cookie",
        )

    try:
        user_id, access_token, new_refresh, _jti, new_exp, access_ttl = (
            await auth_svc.rotate_refresh(cookie_token)
        )
    except auth_svc.AuthError as e:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    _set_refresh_cookie(response, new_refresh, new_exp)
    return TokenResponse(
        access_token=access_token,
        expires_in=access_ttl,
        user_id=user_id,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    """幂等：无 cookie / token 失效都返回 204。"""
    cookie_token = request.cookies.get(settings.refresh_cookie_name, "")
    if cookie_token:
        await auth_svc.revoke_refresh(cookie_token)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        await auth_svc.revoke_access(auth_header[7:].strip())

    _clear_refresh_cookie(response)
    # 204 不返回 body


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.db.models.user import User

    row = (
        await db.execute(select(User.last_login_at).where(User.id == user.id))
    ).scalar_one_or_none()

    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_super=user.is_super,
        roles=sorted(user.role_codes),
        permissions=sorted(user.permission_codes),
        data_scope=user.data_scope,
        last_login_at=row,
    )
