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

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crypto_chart"
    database_echo: bool = False

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_image_type_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_image_types.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
