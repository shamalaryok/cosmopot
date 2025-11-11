"""create billing domain tables

Revision ID: 0002_create_billing_domain
Revises: 0001_create_user_domain
Create Date: 2024-10-30 13:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_create_billing_domain"
down_revision = "0001_create_user_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("subscriptions", "subscription_plans")

    bigint_pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    subscription_tier = sa.Enum(
        "free",
        "standard",
        "pro",
        "enterprise",
        name="subscription_tier",
        native_enum=False,
    )
    subscription_status = sa.Enum(
        "trialing",
        "active",
        "inactive",
        "past_due",
        "canceled",
        "expired",
        name="subscription_status",
        native_enum=False,
    )
    subscription_history_tier = sa.Enum(
        "free",
        "standard",
        "pro",
        "enterprise",
        name="subscription_history_tier",
        native_enum=False,
    )
    subscription_history_status = sa.Enum(
        "trialing",
        "active",
        "inactive",
        "past_due",
        "canceled",
        "expired",
        name="subscription_history_status",
        native_enum=False,
    )
    payment_status = sa.Enum(
        "pending",
        "completed",
        "failed",
        "refunded",
        name="payment_status",
        native_enum=False,
    )
    transaction_type = sa.Enum(
        "charge",
        "refund",
        "credit",
        name="transaction_type",
        native_enum=False,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", subscription_tier, nullable=False),
        sa.Column(
            "status",
            subscription_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "quota_limit", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "quota_used", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("provider_subscription_id", sa.String(length=120), nullable=True),
        sa.Column(
            "provider_data",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "quota_limit >= 0", name="ck_subscriptions_quota_limit_positive"
        ),
        sa.CheckConstraint(
            "quota_used >= 0", name="ck_subscriptions_quota_used_positive"
        ),
        sa.CheckConstraint(
            "quota_used <= quota_limit", name="ck_subscriptions_quota_within_limit"
        ),
        sa.CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_subscriptions_period_order",
        ),
    )
    op.create_index(
        "ix_subscriptions_user_status",
        "subscriptions",
        ["user_id", "status"],
    )
    active_clause = sa.text("status IN ('active', 'trialing')")
    op.create_index(
        "uq_subscriptions_user_active",
        "subscriptions",
        ["user_id"],
        unique=True,
        sqlite_where=active_clause,
        postgresql_where=active_clause,
    )

    op.create_table(
        "subscription_history",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("subscription_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("tier", subscription_history_tier, nullable=False),
        sa.Column("status", subscription_history_status, nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("quota_used", sa.Integer(), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=120), nullable=True),
        sa.Column(
            "provider_data",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_subscription_history_subscription_id",
        "subscription_history",
        ["subscription_id"],
    )

    op.create_table(
        "payments",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            payment_status,
            nullable=False,
            server_default=sa.text("'completed'"),
        ),
        sa.Column("provider_payment_id", sa.String(length=120), nullable=True),
        sa.Column(
            "provider_data",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_subscription_id", "payments", ["subscription_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    provider_id_clause = sa.text("provider_payment_id IS NOT NULL")
    op.create_index(
        "uq_payments_provider_payment_id",
        "payments",
        ["provider_payment_id"],
        unique=True,
        sqlite_where=provider_id_clause,
        postgresql_where=provider_id_clause,
    )

    op.create_table(
        "transactions",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("type", transaction_type, nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_transactions_payment_id", "transactions", ["payment_id"])
    op.create_index(
        "ix_transactions_subscription_id", "transactions", ["subscription_id"]
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_type", "transactions", ["type"])
    provider_ref_clause = sa.text("provider_reference IS NOT NULL")
    op.create_index(
        "uq_transactions_provider_reference",
        "transactions",
        ["provider_reference"],
        unique=True,
        sqlite_where=provider_ref_clause,
        postgresql_where=provider_ref_clause,
    )


def downgrade() -> None:
    op.drop_index("uq_transactions_provider_reference", table_name="transactions")
    op.drop_index("ix_transactions_type", table_name="transactions")
    op.drop_index("ix_transactions_user_id", table_name="transactions")
    op.drop_index("ix_transactions_subscription_id", table_name="transactions")
    op.drop_index("ix_transactions_payment_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("uq_payments_provider_payment_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_subscription_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index(
        "ix_subscription_history_subscription_id",
        table_name="subscription_history",
    )
    op.drop_table("subscription_history")

    op.drop_index("uq_subscriptions_user_active", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_status", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.rename_table("subscription_plans", "subscriptions")
