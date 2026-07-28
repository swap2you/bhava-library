"""Domain error types."""

from __future__ import annotations


class BhavaError(Exception):
    """Base library error."""

    exit_code: int = 30


class ConfigError(BhavaError):
    exit_code = 25


class DiskGuardError(BhavaError):
    exit_code = 20


class NetworkError(BhavaError):
    exit_code = 21


class SourceDriftError(BhavaError):
    exit_code = 22


class AccessRestrictedError(BhavaError):
    exit_code = 23


class IntegrityError(BhavaError):
    exit_code = 24


class BackupVerifyError(BhavaError):
    exit_code = 26


class InvalidStateTransition(BhavaError):
    """Raised when a resource status transition is illegal."""
