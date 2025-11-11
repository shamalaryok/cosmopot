from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.db.types import GUID, UTCDateTime

from .enums import ReferralTier, WithdrawalStatus

if TYPE_CHECKING:
    from backend.auth.models import User
    from backend.payments.models import Payment


class Referral(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Referral relationship between users."""

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referrer_id", "referred_user_id", name="uq_referrals_pair"),
        Index("ix_referrals_referrer_id", "referrer_id"),
        Index("ix_referrals_referred_user_id", "referred_user_id"),
        Index("ix_referrals_referral_code", "referral_code"),
    )

    referrer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referral_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tier: Mapped[ReferralTier] = mapped_column(
        Enum(ReferralTier, name="referral_tier", native_enum=False),
        nullable=False,
        default=ReferralTier.TIER1,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    referrer: Mapped[User] = relationship(
        foreign_keys=[referrer_id],
        back_populates="referrals_made",
    )
    referred_user: Mapped[User] = relationship(
        foreign_keys=[referred_user_id],
        back_populates="referral_received",
    )
    earnings: Mapped[list[ReferralEarning]] = relationship(
        back_populates="referral",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReferralEarning(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Earnings from referral relationships."""

    __tablename__ = "referral_earnings"
    __table_args__ = (
        Index("ix_referral_earnings_referral_id", "referral_id"),
        Index("ix_referral_earnings_user_id", "user_id"),
        Index("ix_referral_earnings_payment_id", "payment_id"),
    )

    referral_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[ReferralTier] = mapped_column(
        Enum(ReferralTier, name="referral_earning_tier", native_enum=False),
        nullable=False,
    )

    referral: Mapped[Referral] = relationship(back_populates="earnings")
    user: Mapped[User] = relationship(back_populates="referral_earnings")
    payment: Mapped[Payment] = relationship()


class ReferralWithdrawal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Withdrawal requests for referral earnings."""

    __tablename__ = "referral_withdrawals"
    __table_args__ = (
        Index("ix_referral_withdrawals_user_id", "user_id"),
        Index("ix_referral_withdrawals_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus, name="withdrawal_status", native_enum=False),
        nullable=False,
        default=WithdrawalStatus.PENDING,
    )
    processed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    notes: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship(back_populates="referral_withdrawals")
