from __future__ import annotations

from typing import Any, Protocol

import structlog

from user_service.models import User

from .enums import PaymentStatus
from .models import Payment


class PaymentNotifier(Protocol):
    """Abstraction responsible for surfacing payment status changes to the user."""

    async def notify(
        self,
        user: User,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        """Dispatch a notification (email, Telegram, webhook, etc.)"""


class LoggingPaymentNotifier:
    """Default notifier that logs status changes in lieu of an external integration."""

    def __init__(self) -> None:
        self._logger = structlog.get_logger(__name__)

    async def notify(
        self,
        user: User,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        self._logger.info(
            "payment_status_changed",
            user_id=user.id,
            payment_id=str(payment.id),
            status=status.value,
            context=context,
        )
