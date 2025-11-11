from __future__ import annotations


class PaymentError(RuntimeError):
    """Base class for payment domain errors."""


class PaymentConfigurationError(PaymentError):
    """Raised when the payment integration is not properly configured."""


class PaymentPlanNotFoundError(PaymentError):
    """Raised when a requested pricing tier or plan is unknown."""


class PaymentGatewayError(PaymentError):
    """Raised when the upstream payment provider rejects a request."""


class PaymentNotFoundError(PaymentError):
    """Raised when a payment referenced by provider identifiers is missing."""


class PaymentSignatureError(PaymentError):
    """Raised when an incoming webhook fails signature verification."""
