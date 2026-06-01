"""统一配置入口（Pydantic Settings → 从 .env 加载）。

放在 app/config.py，所有模块通过 `from app.config import settings` 取值，
禁止直接 os.environ.get。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 基础
    env: str = "dev"
    debug: bool = True

    # PG
    database_url: str = "postgresql+asyncpg://tcalpha:dev@localhost:5432/tcalpha"
    database_url_sync: str = "postgresql+psycopg2://tcalpha:dev@localhost:5432/tcalpha"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ArcticDB
    arctic_uri: str = "lmdb://./data/arctic"

    # JWT（Phase 7 RBAC）
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    # access token：内存，15min
    jwt_access_expire_minutes: int = 15
    # refresh token：HttpOnly cookie，30 天
    jwt_refresh_expire_days: int = 30
    # 兼容旧字段（早期 Basic Auth 阶段）
    jwt_expire_minutes: int = 60 * 24 * 30

    # Refresh Cookie
    refresh_cookie_name: str = "tcalpha_refresh"
    refresh_cookie_path: str = "/api/auth"
    # 生产置 true（https + secure）；dev 留 false
    refresh_cookie_secure: bool = False
    # 防 CSRF：strict / lax / none
    refresh_cookie_samesite: str = "strict"

    # 默认用户（个人版临时占位）
    default_user_id: int = 1

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Basic Auth（Phase 6 上线必备）
    auth_enabled: bool = False
    auth_username: str = "admin"
    # bcrypt hash；用 scripts/gen_password_hash.py 生成
    auth_password_hash: str = ""
    # 即使开启鉴权，也保留这些路径无需认证：
    auth_public_paths: str = "/health,/"
    # /docs /redoc /openapi.json 是否随鉴权一并保护（防扫描）
    auth_protect_docs: bool = True

    # AI
    ai_api_base: str = "https://api.deepseek.com/v1"
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"

    # AKShare
    akshare_rate_limit: int = 2

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_public_paths_list(self) -> list[str]:
        return [p.strip() for p in self.auth_public_paths.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
