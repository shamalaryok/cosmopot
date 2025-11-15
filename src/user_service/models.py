from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, TypeAlias

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from common.sqlalchemy import MetadataAliasMixin

from .enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)

# Type alias for JSON dictionary columns
JSONDict: TypeAlias = dict[str, Any]

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _generation_status_values(
    enum_cls: type[GenerationTaskStatus],
) -> list[str]:
    return [member.value for member in enum_cls]


class Base(DeclarativeBase):
    """Base class for declarative models."""

    metadata: ClassVar[MetaData]

    type_annotation_map: ClassVar[dict[type[Any], Any]] = {
        dict: JSON,
    }


# Set the metadata with naming conventions on the registry
Base.registry.metadata = metadata


class SubscriptionPlan(Base):
    """Represents an available subscription plan template."""

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    monthly_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list[User]] = relationship(
        back_populates="subscription_plan", passive_deletes=True
    )


class User(Base):
    """Stores core authentication and account information for a person."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.USER,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0"), default=Decimal("0")
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped[UserProfile] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    subscription_plan: Mapped[SubscriptionPlan | None] = relationship(
        back_populates="users"
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    generation_tasks: Mapped[list[GenerationTask]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


Index("ix_users_role", User.role)


class UserProfile(Base):
    """Stores extended profile information for a user."""

    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_profiles_user_id"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="profile")


Index("ix_user_profiles_user_id", UserProfile.user_id)


class UserSession(Base):
    """Tracks authentication sessions for a user."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("session_token", name="uq_user_sessions_session_token"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_token: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="sessions")


Index("ix_user_sessions_user_id", UserSession.user_id)


class Subscription(Base, MetadataAliasMixin):
    """Tracks the lifecycle of a user's billing subscription."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        CheckConstraint(
            "quota_limit >= 0", name="ck_subscriptions_quota_limit_positive"
        ),
        CheckConstraint("quota_used >= 0", name="ck_subscriptions_quota_used_positive"),
        CheckConstraint(
            "quota_used <= quota_limit", name="ck_subscriptions_quota_within_limit"
        ),
        CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_subscriptions_period_order",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_tier", native_enum=False),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        server_default=text("'active'"),
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    quota_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    quota_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120))
    provider_data: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    history: Mapped[list[SubscriptionHistory]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


Index("ix_subscriptions_user_status", Subscription.user_id, Subscription.status)
Index(
    "uq_subscriptions_user_active",
    Subscription.user_id,
    unique=True,
    sqlite_where=text("status IN ('active', 'trialing')"),
    postgresql_where=text("status IN ('active', 'trialing')"),
)


class SubscriptionHistory(Base, MetadataAliasMixin):
    """Immutable snapshots capturing subscription changes."""

    __tablename__ = "subscription_history"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_history_tier", native_enum=False),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_history_status",
            native_enum=False,
        ),
        nullable=False,
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quota_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_used: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120))
    provider_data: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="history")


Index(
    "ix_subscription_history_subscription_id",
    SubscriptionHistory.subscription_id,
)


class Payment(Base, MetadataAliasMixin):
    """Represents a monetary settlement attempt for a subscription."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        default=PaymentStatus.COMPLETED,
        server_default=text("'completed'"),
    )
    provider_payment_id: Mapped[str | None] = mapped_column(String(120))
    provider_data: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subscription: Mapped[Subscription | None] = relationship(back_populates="payments")
    user: Mapped[User] = relationship(back_populates="payments")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", passive_deletes=True
    )


Index("ix_payments_user_id", Payment.user_id)
Index("ix_payments_subscription_id", Payment.subscription_id)
Index("ix_payments_status", Payment.status)
Index(
    "uq_payments_provider_payment_id",
    Payment.provider_payment_id,
    unique=True,
    sqlite_where=text("provider_payment_id IS NOT NULL"),
    postgresql_where=text("provider_payment_id IS NOT NULL"),
)


class Transaction(Base, MetadataAliasMixin):
    """Ledger line item tied to a payment and optionally a subscription."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(255))
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payment: Mapped[Payment] = relationship(back_populates="transactions")
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="transactions"
    )
    user: Mapped[User] = relationship(back_populates="transactions")


Index("ix_transactions_payment_id", Transaction.payment_id)
Index("ix_transactions_subscription_id", Transaction.subscription_id)
Index("ix_transactions_user_id", Transaction.user_id)
Index("ix_transactions_type", Transaction.type)
Index(
    "uq_transactions_provider_reference",
    Transaction.provider_reference,
    unique=True,
    sqlite_where=text("provider_reference IS NOT NULL"),
    postgresql_where=text("provider_reference IS NOT NULL"),
)


class Prompt(Base):
    """Describes a reusable prompt template for generation tasks."""

    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_prompts_slug_version"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[PromptCategory] = mapped_column(
        Enum(PromptCategory, name="prompt_category", native_enum=False),
        nullable=False,
        default=PromptCategory.GENERIC,
        server_default=text("'generic'"),
    )
    source: Mapped[PromptSource] = mapped_column(
        Enum(PromptSource, name="prompt_source", native_enum=False),
        nullable=False,
        default=PromptSource.SYSTEM,
        server_default=text("'system'"),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    parameters_schema: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    parameters: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    preview_asset_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tasks: Mapped[list[GenerationTask]] = relationship(
        back_populates="prompt",
        passive_deletes=True,
    )


class GenerationTask(Base):
    """Tracks the lifecycle and artifacts of a generation request."""

    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[GenerationTaskStatus] = mapped_column(
        Enum(
            GenerationTaskStatus,
            name="generation_task_status",
            native_enum=False,
            values_callable=_generation_status_values,
        ),
        nullable=False,
        default=GenerationTaskStatus.PENDING,
        server_default=text("'pending'"),
    )
    source: Mapped[GenerationTaskSource] = mapped_column(
        Enum(GenerationTaskSource, name="generation_task_source", native_enum=False),
        nullable=False,
        default=GenerationTaskSource.API,
        server_default=text("'api'"),
    )
    parameters: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    result_parameters: Mapped[JSONDict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    input_asset_url: Mapped[str | None] = mapped_column(String(2048))
    result_asset_url: Mapped[str | None] = mapped_column(String(2048))
    error: Mapped[str | None] = mapped_column(String(500))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    prompt: Mapped[Prompt] = relationship(back_populates="tasks")
    user: Mapped[User] = relationship(back_populates="generation_tasks")


Index("ix_prompts_slug", Prompt.slug)
Index("ix_prompts_category", Prompt.category)
Index("ix_prompts_slug_active", Prompt.slug, Prompt.is_active)
Index(
    "ix_prompts_slug_version_desc",
    Prompt.slug,
    Prompt.version.desc(),
)
Index(
    "ix_generation_tasks_user_status",
    GenerationTask.user_id,
    GenerationTask.status,
)
Index("ix_generation_tasks_prompt_id", GenerationTask.prompt_id)
