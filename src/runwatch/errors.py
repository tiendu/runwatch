from __future__ import annotations


class RunwatchError(Exception):
    """Base class for expected Runwatch failures shown without a traceback."""


class ConfigError(RunwatchError):
    """Raised when a Runwatch configuration cannot be loaded or validated."""


class OutputError(RunwatchError):
    """Raised when Runwatch cannot safely create or replace an output file."""


class InstallationError(RunwatchError):
    """Raised when persistent service installation cannot be completed safely."""


class UsageError(RunwatchError):
    """Raised when parsed arguments form an invalid command combination."""


class TemplateError(RunwatchError):
    """Raised when a generated deployment template would be invalid."""


class ServiceError(RunwatchError):
    """Raised when the persistent monitoring service cannot start cleanly."""
