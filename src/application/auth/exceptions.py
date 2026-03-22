"""Domain-level exceptions for auth."""


class AuthError(Exception):
    """Raised when MAX authentication fails."""


class SessionExpiredError(AuthError):
    """Raised when a stored session can no longer be used."""
