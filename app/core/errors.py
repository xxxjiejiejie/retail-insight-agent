class RetailInsightError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(RetailInsightError):
    """Raised when a required integration is not configured."""


class UnsafeSQLError(RetailInsightError):
    """Raised when generated SQL violates the read-only policy."""

