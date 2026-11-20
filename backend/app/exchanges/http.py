"""Shared HTTP helpers: timeouts, retries, exponential backoff."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from app.exchanges.exceptions import ExchangeRateLimitError, ExchangeRequestError
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    exchange: str,
    retries: int = 3,
    base_delay: float = 0.4,
) -> T:
    """
    Retry transient failures (rate limits / 5xx / network) with exponential backoff.
    Non-retryable 4xx errors are raised immediately.
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return await operation()
        except ExchangeRateLimitError as exc:
            last_error = exc
            delay = base_delay * (2**attempt)
            logger.warning(
                "%s rate-limited (attempt %s/%s); sleeping %.2fs",
                exchange,
                attempt + 1,
                retries,
                delay,
            )
            await asyncio.sleep(delay)
        except ExchangeRequestError as exc:
            last_error = exc
            status = exc.status_code or 0
            if status and 400 <= status < 500 and status != 429:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "%s request error %s (attempt %s/%s); sleeping %.2fs",
                exchange,
                status or exc,
                attempt + 1,
                retries,
                delay,
            )
            await asyncio.sleep(delay)
        except httpx.TimeoutException as exc:
            last_error = ExchangeRequestError(
                f"{exchange} timeout: {exc}",
                exchange=exchange,
            )
            delay = base_delay * (2**attempt)
            logger.warning(
                "%s timeout (attempt %s/%s); sleeping %.2fs",
                exchange,
                attempt + 1,
                retries,
                delay,
            )
            await asyncio.sleep(delay)
        except httpx.HTTPError as exc:
            last_error = ExchangeRequestError(
                f"{exchange} network error: {exc}",
                exchange=exchange,
            )
            delay = base_delay * (2**attempt)
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error
