"""
Domain exception hierarchy.

Service-layer code raises these instead of returning ad-hoc error tuples or
raising ``ValueError``. The API layer translates them into HTTP responses via
:mod:`common.exceptions.handlers`, so business rules stay independent of DRF.

Existing code raises ``ValueError`` for insufficient balance (see
``UserCoinBalance.spend_coins``). That is unchanged; :class:`InsufficientFunds`
exists for new service code and for a future migration of those call sites.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for business-rule violations."""

    #: Machine-readable code returned to API clients.
    code = 'domain_error'
    #: Default message when none is supplied.
    default_message = 'The operation could not be completed.'
    #: HTTP status the API layer should map this to.
    status_code = 400

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.default_message
        self.context = context
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {'error': self.message, 'code': self.code}
        if self.context:
            payload.update(self.context)
        return payload


class ValidationError(DomainError):
    """Input failed a business-rule check (as opposed to a schema check)."""

    code = 'validation_error'
    default_message = 'The supplied data is not valid.'
    status_code = 400


class NotFound(DomainError):
    """A referenced entity does not exist."""

    code = 'not_found'
    default_message = 'The requested resource was not found.'
    status_code = 404


class PermissionDenied(DomainError):
    """The caller is authenticated but not allowed to perform this action."""

    code = 'permission_denied'
    default_message = 'You do not have permission to perform this action.'
    status_code = 403


class ConflictError(DomainError):
    """The action conflicts with the current state of the resource."""

    code = 'conflict'
    default_message = 'The request conflicts with the current state.'
    status_code = 409


# ---------------------------------------------------------------------------
# Financial domain
# ---------------------------------------------------------------------------


class FinancialError(DomainError):
    """Base class for wallet, payment and settlement failures."""

    code = 'financial_error'
    default_message = 'The financial operation could not be completed.'


class InsufficientFunds(FinancialError):
    """The account does not hold enough of the required currency."""

    code = 'insufficient_funds'
    default_message = 'Insufficient balance for this operation.'

    def __init__(self, available: int | None = None, required: int | None = None, **context: Any):
        message = self.default_message
        if available is not None and required is not None:
            message = f'Insufficient balance. Available {available}, required {required}.'
        super().__init__(message, available=available, required=required, **context)


class DuplicateTransaction(FinancialError):
    """A transaction with this idempotency key or provider reference exists."""

    code = 'duplicate_transaction'
    default_message = 'This transaction has already been processed.'
    status_code = 409


class InvalidStateTransition(FinancialError):
    """The requested state change is not legal from the current state."""

    code = 'invalid_state_transition'
    default_message = 'This transaction cannot move to the requested state.'
    status_code = 409


# ---------------------------------------------------------------------------
# External providers
# ---------------------------------------------------------------------------


class IntegrationError(DomainError):
    """An external provider failed, timed out, or returned an unusable result."""

    code = 'integration_error'
    default_message = 'An external service is currently unavailable.'
    status_code = 502

    def __init__(self, provider: str, message: str | None = None, **context: Any) -> None:
        self.provider = provider
        super().__init__(
            message or f'{provider} is currently unavailable.', provider=provider, **context
        )


class IntegrationTimeout(IntegrationError):
    """The provider did not respond within the configured timeout.

    Distinct from :class:`IntegrationError` because a timeout leaves the remote
    outcome *unknown* -- the operation may still have succeeded. Callers must
    reconcile rather than assume failure.
    """

    code = 'integration_timeout'
    status_code = 504


class SignatureVerificationError(IntegrationError):
    """A webhook or callback failed signature verification."""

    code = 'signature_verification_failed'
    status_code = 400


# ---------------------------------------------------------------------------
# End-to-end encryption
# ---------------------------------------------------------------------------


class DecryptionError(DomainError):
    """An encrypted payload could not be decrypted or failed integrity checks.

    Deliberately generic. The underlying cause (bad key, corrupt ciphertext,
    wrong nonce, tampered payload) is not distinguished in the response --
    doing so would let an attacker use the error message as an oracle to
    probe which part of a forged payload is wrong.
    """

    code = 'decryption_failed'
    default_message = 'The payload could not be decrypted.'
    status_code = 400


class EncryptionUnavailable(DomainError):
    """The service cannot seal a response for an encrypted endpoint.

    Raised when the server keypair cannot be retrieved (key store unreachable,
    key never provisioned). This is deliberately raised during request dispatch
    rather than left to surface from the renderer: a renderer runs *after*
    DRF's exception handler, so anything it raises escapes to Django and
    becomes an unhandled HTML 500 -- which is how a key-store outage
    previously presented to clients.

    503 rather than 500: the request is well-formed and retryable once the key
    store is healthy again.
    """

    code = 'encryption_unavailable'
    default_message = 'Secure transport is temporarily unavailable. Please retry.'
    status_code = 503


class ReplayDetected(DomainError):
    """An encrypted payload's nonce has already been used once before.

    A NaCl box nonce must never be reused for a given key pair, and a message
    an attacker resends verbatim will carry a nonce this service has already
    seen. Treated as a security event, not an integrity failure.
    """

    code = 'replay_detected'
    default_message = 'This payload has already been processed.'
    status_code = 409
