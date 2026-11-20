"""Shared AI status helpers."""

from __future__ import annotations

from enum import Enum


class AiStatus(str, Enum):
    OK = "OK"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_MODEL_RESPONSE = "INVALID_MODEL_RESPONSE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ERROR = "ERROR"


def openai_configured(api_key: str | None) -> bool:
    return bool(api_key and api_key.strip())
