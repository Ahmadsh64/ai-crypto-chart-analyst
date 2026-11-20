"""Security helpers for API key handling and request validation."""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_optional_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    """
    Optional API-key gate for future authenticated routes.

    Phase 1 does not require a key. When APP_API_KEY is set in the environment,
    matching requests are accepted; mismatched keys are rejected.
    """
    settings = get_settings()
    expected = getattr(settings, "app_api_key", None)
    if not expected:
        return x_api_key
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
