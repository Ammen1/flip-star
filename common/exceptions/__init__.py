"""Domain exception hierarchy and the DRF exception handler."""

from common.exceptions.base import (
    ConflictError,
    DecryptionError,
    DomainError,
    DuplicateTransaction,
    FinancialError,
    InsufficientFunds,
    IntegrationError,
    IntegrationTimeout,
    InvalidStateTransition,
    NotFound,
    PermissionDenied,
    ReplayDetected,
    SignatureVerificationError,
    ValidationError,
)

__all__ = [
    'ConflictError', 'DecryptionError', 'DomainError', 'DuplicateTransaction',
    'FinancialError', 'IntegrationError', 'IntegrationTimeout',
    'InsufficientFunds', 'InvalidStateTransition', 'NotFound',
    'PermissionDenied', 'ReplayDetected', 'SignatureVerificationError',
    'ValidationError',
]
