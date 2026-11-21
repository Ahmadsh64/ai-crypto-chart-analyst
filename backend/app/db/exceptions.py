"""Persistence-layer exceptions (Phase 6.0.2)."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base persistence error."""

    code: str = "PERSISTENCE_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class PersistenceDisabledError(PersistenceError):
    code = "PERSISTENCE_DISABLED"


class PersistenceUnavailableError(PersistenceError):
    code = "PERSISTENCE_UNAVAILABLE"


class IdempotencyConflictError(PersistenceError):
    """Same identity key with a different payload hash — never overwrite."""

    code = "IDEMPOTENCY_CONFLICT"

    def __init__(
        self,
        message: str,
        *,
        identity_key: str | None = None,
        existing_hash: str | None = None,
        incoming_hash: str | None = None,
    ) -> None:
        super().__init__(message, code=self.code)
        self.identity_key = identity_key
        self.existing_hash = existing_hash
        self.incoming_hash = incoming_hash
