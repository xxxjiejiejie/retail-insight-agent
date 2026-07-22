class RetailInsightError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(RetailInsightError):
    """Raised when a required integration is not configured."""


class UnsafeSQLError(RetailInsightError):
    """Raised when generated SQL violates the read-only policy."""


class IntegrationError(RetailInsightError):
    """Raised when an external service request fails."""


class LLMResponseError(RetailInsightError):
    """Raised when an LLM response cannot be parsed or validated."""


class DatabaseQueryError(RetailInsightError):
    """Raised when an approved read-only query cannot be executed."""
