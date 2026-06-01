"""JWT 签发 / 验签 / 黑名单（Phase 7 RBAC Step 2）。

设计：
- access token：HS256，15min，仅放 sub（user_id）+ type=access + jti
- refresh token：HS256，30 天，sub + type=refresh + jti（用于 logout 黑名单）
- 黑名单：Redis key `auth:bl:<jti>`，TTL = token 剩余有效期；命中即失效
- 密码：bcrypt 直接调用，72 字节截断（passlib 与 bcrypt 5.x 兼容问题）
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.db.redis_client import get_redis

# ── 常量 ────────────────────────────────────────────────────────────
TOKEN_TYPE_ACCESS: Final = "access"
TOKEN_TYPE_REFRESH: Final = "refresh"

_BCRYPT_MAX: Final = 72
_BL_PREFIX: Final = "auth:bl:"


# ── 密码 ────────────────────────────────────────────────────────────
def _truncate(plain: str) -> bytes:
    """bcrypt 上限 72 字节，超长截断（与 Phase 6 Basic Auth 保持一致）。"""
    return plain.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_truncate(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT 签发 ────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> tuple[str, str, datetime]:
    """返回 (token, jti, exp_utc)。"""
    jti = uuid.uuid4().hex
    exp = _now() + timedelta(minutes=settings.jwt_access_expire_minutes)
    token = _encode(
        {
            "sub": str(user_id),
            "type": TOKEN_TYPE_ACCESS,
            "jti": jti,
            "iat": int(_now().timestamp()),
            "exp": int(exp.timestamp()),
        }
    )
    return token, jti, exp


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """返回 (token, jti, exp_utc)。"""
    jti = uuid.uuid4().hex
    exp = _now() + timedelta(days=settings.jwt_refresh_expire_days)
    token = _encode(
        {
            "sub": str(user_id),
            "type": TOKEN_TYPE_REFRESH,
            "jti": jti,
            "iat": int(_now().timestamp()),
            "exp": int(exp.timestamp()),
        }
    )
    return token, jti, exp


# ── JWT 验签 ────────────────────────────────────────────────────────
class TokenError(Exception):
    """JWT 校验失败（签名/格式/过期/类型/黑名单）。"""


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    """解析并校验 JWT。

    expected_type 指定时校验 payload["type"] 必须匹配（防止 access/refresh 混用）。
    过期 / 签名错 / 类型不符均抛 TokenError。
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as e:
        raise TokenError(f"jwt decode failed: {e}") from e

    if expected_type and payload.get("type") != expected_type:
        raise TokenError(
            f"token type mismatch: expected {expected_type}, got {payload.get('type')}"
        )
    if "sub" not in payload or "jti" not in payload:
        raise TokenError("token missing sub/jti")
    return payload


# ── 黑名单 ──────────────────────────────────────────────────────────
async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """把 jti 拉黑，TTL 默认到 token 自然过期时间。"""
    if ttl_seconds <= 0:
        return
    r = get_redis()
    await r.setex(f"{_BL_PREFIX}{jti}", ttl_seconds, "1")


async def is_jti_blacklisted(jti: str) -> bool:
    r = get_redis()
    return bool(await r.exists(f"{_BL_PREFIX}{jti}"))


def ttl_from_payload(payload: dict[str, Any]) -> int:
    """从 payload.exp 算剩余秒数（最少 0）。"""
    exp = int(payload.get("exp", 0))
    remain = exp - int(_now().timestamp())
    return max(remain, 0)
