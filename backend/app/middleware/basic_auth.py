"""HTTP Basic Auth 中间件（Phase 6 v0.6.0）。

特点：
- ASGI 层中间件，同时拦截 HTTP 与 WebSocket
- 公共白名单走 `settings.auth_public_paths`
- WebSocket 不能传 header，回退到 query `?token=base64(user:pass)`
- bcrypt 比对，常数时间检查
"""
from __future__ import annotations

import base64
import binascii
from urllib.parse import parse_qs

import bcrypt
from loguru import logger
from starlette.types import ASGIApp, Receive, Scope, Send

# bcrypt 限制密码 72 字节；这里做安全截断（与 hash 时一致）
_BCRYPT_MAX = 72


def _truncate(plain: str) -> bytes:
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


def _decode_basic(value: str) -> tuple[str, str] | None:
    """从 'Basic xxx' / 裸 base64 解出 (user, pass)。"""
    if value.startswith("Basic "):
        value = value[6:].strip()
    try:
        raw = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in raw:
        return None
    user, _, pwd = raw.partition(":")
    return user, pwd


class BasicAuthMiddleware:
    """ASGI 中间件，覆盖 HTTP + WebSocket 双协议。"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        username: str,
        password_hash: str,
        public_paths: list[str],
        protect_docs: bool,
    ) -> None:
        self.app = app
        self.username = username
        self.password_hash = password_hash
        self.public_paths = set(public_paths)
        self.protect_docs = protect_docs

    def _is_public(self, path: str) -> bool:
        if path in self.public_paths:
            return True
        return not self.protect_docs and path in {"/docs", "/redoc", "/openapi.json"}

    def _check(self, user: str, pwd: str) -> bool:
        return user == self.username and verify_password(pwd, self.password_hash)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        if self._is_public(path):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers") or []}

        # 1. Authorization header
        auth_header = headers.get("authorization", "")
        if auth_header:
            creds = _decode_basic(auth_header)
            if creds and self._check(*creds):
                await self.app(scope, receive, send)
                return

        # 2. 兜底：query string token（浏览器 WS 不能带 header）
        qs = scope.get("query_string", b"")
        if qs:
            params = parse_qs(qs.decode("utf-8", errors="ignore"))
            token = (params.get("token") or [""])[0]
            if token:
                creds = _decode_basic(token)
                if creds and self._check(*creds):
                    await self.app(scope, receive, send)
                    return

        await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            # 1008 = policy violation
            await send({"type": "websocket.close", "code": 1008, "reason": "unauthorized"})
            logger.info("WS auth failed: {}", scope.get("path"))
            return

        body = b'{"detail":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Basic realm="TCAlpha"'),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
