"""Configuration failures. All of them abort startup."""

from __future__ import annotations


class ConfigurationError(RuntimeError):
    """
    Raised when runtime configuration cannot be loaded or is incomplete.

    Never carries a secret value. The message names the Vault path and the key,
    which is what an operator needs to fix it, and nothing more -- these
    messages reach logs, crash reporters and terminal output, none of which
    should ever hold a credential.
    """

    def __init__(self, message: str, *, path: str | None = None, key: str | None = None):
        self.path = path
        self.key = key
        super().__init__(message)


class VaultUnreachable(ConfigurationError):
    """Vault could not be contacted, or refused authentication."""


class MissingConfiguration(ConfigurationError):
    """A required key is absent, or present but empty."""


class InvalidConfiguration(ConfigurationError):
    """A key is present but its value cannot be used (wrong type, bad format)."""
