"""
Raised when the application's cryptographic identity keypair cannot be
safely established or used.

Deliberately NOT a subclass of ``common.exceptions.DomainError``: those exist
to turn a single request's business-rule violation into an HTTP response.
This is an operational/boot-time failure -- Redis unreachable, or the stored
keypair is missing a half or doesn't match -- that should stop the process
from starting, not be handled per-request. The one place this does reach an
HTTP response is the public-key endpoint, which catches it explicitly and
returns 503, not any of the 4xx codes ``DomainError`` maps to.
"""


class KeyManagementError(RuntimeError):
    pass
