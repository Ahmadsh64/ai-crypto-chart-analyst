"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration for the API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Crypto Chart Analyst"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production", "demo"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # Database / Supabase PostgreSQL (Phase 6.0.2) — never expose to frontend
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crypto_chart"
    database_echo: bool = False
    # Optional persistence — disabled by default; app runs without Supabase
    persistence_enabled: bool = False
    # Prefer DATABASE_URL; optional Supabase-specific overrides (server-only)
    supabase_db_url: str = ""
    supabase_db_host: str = ""
    supabase_db_port: int = 5432
    supabase_db_name: str = "postgres"
    supabase_db_user: str = "postgres"
    supabase_db_password: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: float = 30.0
    db_connect_timeout_seconds: float = 10.0
    # Server-only path to Supabase Root CA PEM (relative paths resolve from backend/)
    supabase_ssl_ca_file: str = ""

    # Redis (optional)
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    # OpenAI (Phase 5.4 — never expose to frontend)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_vision_model: str = "gpt-4o"
    openai_explainer_model: str = "gpt-4o"
    openai_timeout_seconds: float = 60.0
    openai_max_retries: int = 1

    # Exchange public endpoints — no trading keys required for Phase 1–2
    binance_base_url: str = "https://api.binance.com"
    binance_futures_base_url: str = "https://fapi.binance.com"
    bybit_base_url: str = "https://api.bybit.com"

    # Risk defaults
    default_account_balance: float = 10_000.0
    default_risk_percent: float = 1.0
    default_min_risk_reward: float = 2.0
    max_risk_percent: float = 5.0

    # Uploads (Phase 5.4 vision)
    max_upload_size_mb: int = 10
    allowed_image_types: str = "image/png,image/jpeg,image/jpg,image/webp"
    max_image_width: int = 4096
    max_image_height: int = 4096
    min_image_width: int = 64
    min_image_height: int = 64

    # Demo / mock mode for UI development without live exchange calls
    demo_mode: bool = False

    # --- Auth (Supabase Auth JWT) — server-only; never put secrets in NEXT_PUBLIC_ ---
    # When false (default), REST/WS behave as unauthenticated local/dev/tests.
    # Production: AUTH_ENABLED=true + SUPABASE_URL + SUPABASE_ANON_KEY + allowlist.
    # ES256 verified via JWKS; legacy HS256 verified via Supabase Auth /auth/v1/user.
    auth_enabled: bool = False
    supabase_url: str = ""
    # Public anon/publishable key (server-side copy for Auth user lookup). Not a private key.
    supabase_anon_key: str = ""
    # Optional / unused for verification when using JWKS + remote HS256 (kept for ops notes).
    supabase_jwt_secret: str = ""
    # Comma-separated owner emails allowed to use the API (case-insensitive).
    auth_allowed_emails: str = ""
    # OpenAPI docs: off in production unless explicitly re-enabled.
    docs_enabled: bool | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def auth_allowed_email_list(self) -> list[str]:
        return [
            email.strip().lower()
            for email in self.auth_allowed_emails.split(",")
            if email.strip()
        ]

    @property
    def supabase_auth_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def openapi_docs_enabled(self) -> bool:
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.environment != "production"

    @property
    def allowed_image_type_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_image_types.split(",") if t.strip()]

    @property
    def effective_database_url(self) -> str:
        """Resolve async SQLAlchemy URL for Supabase/Postgres (asyncpg)."""
        if self.supabase_db_url.strip():
            return self._ensure_asyncpg_url(self.supabase_db_url.strip())
        if (
            self.supabase_db_host.strip()
            and self.supabase_db_password
            and self.persistence_enabled
        ):
            user = self.supabase_db_user or "postgres"
            host = self.supabase_db_host.strip()
            port = self.supabase_db_port or 5432
            name = self.supabase_db_name or "postgres"
            from urllib.parse import quote_plus

            password = quote_plus(self.supabase_db_password)
            return (
                f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
            )
        return self._ensure_asyncpg_url(self.database_url)

    @staticmethod
    def _ensure_asyncpg_url(url: str) -> str:
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
