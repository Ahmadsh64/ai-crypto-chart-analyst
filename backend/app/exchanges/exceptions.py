"""Exchange-layer exceptions."""


class ExchangeError(Exception):
    """Base exchange error."""

    def __init__(self, message: str, *, exchange: str | None = None) -> None:
        self.exchange = exchange
        super().__init__(message)


class ExchangeUnsupportedError(ExchangeError):
    """Requested market type or timeframe is not supported."""


class ExchangeRequestError(ExchangeError):
    """Upstream HTTP / API failure."""

    def __init__(
        self,
        message: str,
        *,
        exchange: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, exchange=exchange)


class ExchangeRateLimitError(ExchangeRequestError):
    """Upstream rate limit hit."""
