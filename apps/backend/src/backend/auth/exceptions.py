from __future__ import annotations


class AuthError(Exception):
    """Base class for authentication related errors."""


class EmailAlreadyRegisteredError(AuthError):
    """Raised when attempting to register an email that already exists."""


class InvalidCredentialsError(AuthError):
    """Raised when credentials supplied by the client are invalid."""


class AccountNotVerifiedError(AuthError):
    """Raised when a user attempts to authenticate without verifying their account."""


class AccountDisabledError(AuthError):
    """Raised when an inactive account is used during authentication."""


class VerificationTokenInvalidError(AuthError):
    """Raised when an account verification token is invalid or expired."""


class TokenExpiredError(AuthError):
    """Raised when a JWT has expired."""


class InvalidTokenError(AuthError):
    """Raised when a token is malformed or cannot be validated."""


class SessionRevokedError(AuthError):
    """Raised when the session referenced by a token is no longer valid."""
