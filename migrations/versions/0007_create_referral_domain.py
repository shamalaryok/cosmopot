"""create referral domain tables

Revision ID: 0007_create_referral_domain
Revises: 0002_create_billing_domain
Create Date: 2024-11-06 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_create_referral_domain"
down_revision = "0002_create_billing_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use proper UUID type that works across databases
    try:
        uuid_type = sa.Uuid()
    except AttributeError:
        # Fallback for older SQLAlchemy versions
        uuid_type = sa.String(36)
    
    referral_tier = sa.Enum(
        "tier1",
        "tier2",
        name="referral_tier",
        native_enum=False,
    )
    withdrawal_status = sa.Enum(
        "pending",
        "approved",
        "rejected",
        "processed",
        name="withdrawal_status",
        native_enum=False,
    )
    referral_earning_tier = sa.Enum(
        "tier1",
        "tier2",
        name="referral_earning_tier",
        native_enum=False,
    )

    # Create referrals table
    op.create_table(
        "referrals",
        sa.Column("id", uuid_type, primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("referrer_id", uuid_type, nullable=False),
        sa.Column("referred_user_id", uuid_type, nullable=False),
        sa.Column("referral_code", sa.String(length=32), nullable=False),
        sa.Column("tier", referral_tier, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
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
        sa.ForeignKeyConstraint(
            ["referrer_id"], ["auth_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["referred_user_id"], ["auth_users.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("referrer_id", "referred_user_id", name="uq_referrals_pair"),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])
    op.create_index("ix_referrals_referred_user_id", "referrals", ["referred_user_id"])
    op.create_index("ix_referrals_referral_code", "referrals", ["referral_code"])

    # Create referral_earnings table
    op.create_table(
        "referral_earnings",
        sa.Column("id", uuid_type, primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("referral_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("payment_id", uuid_type, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("percentage", sa.Integer(), nullable=False),
        sa.Column("tier", referral_earning_tier, nullable=False),
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
        sa.ForeignKeyConstraint(
            ["referral_id"], ["referrals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_referral_earnings_referral_id", "referral_earnings", ["referral_id"])
    op.create_index("ix_referral_earnings_user_id", "referral_earnings", ["user_id"])
    op.create_index("ix_referral_earnings_payment_id", "referral_earnings", ["payment_id"])

    # Create referral_withdrawals table
    op.create_table(
        "referral_withdrawals",
        sa.Column("id", uuid_type, primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", withdrawal_status, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth_users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_referral_withdrawals_user_id", "referral_withdrawals", ["user_id"])
    op.create_index("ix_referral_withdrawals_status", "referral_withdrawals", ["status"])
    
    # Additional indexes for performance
    op.create_index("ix_referral_earnings_created_at", "referral_earnings", ["created_at"])
    op.create_index("ix_referral_withdrawals_created_at", "referral_withdrawals", ["created_at"])
    op.create_index("ix_referrals_created_at", "referrals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_referrals_created_at", table_name="referrals")
    op.drop_index("ix_referral_withdrawals_created_at", table_name="referral_withdrawals")
    op.drop_index("ix_referral_earnings_created_at", table_name="referral_earnings")
    op.drop_index("ix_referral_withdrawals_status", table_name="referral_withdrawals")
    op.drop_index("ix_referral_withdrawals_user_id", table_name="referral_withdrawals")
    op.drop_table("referral_withdrawals")

    op.drop_index("ix_referral_earnings_payment_id", table_name="referral_earnings")
    op.drop_index("ix_referral_earnings_user_id", table_name="referral_earnings")
    op.drop_index("ix_referral_earnings_referral_id", table_name="referral_earnings")
    op.drop_table("referral_earnings")

    op.drop_index("ix_referrals_referral_code", table_name="referrals")
    op.drop_index("ix_referrals_referred_user_id", table_name="referrals")
    op.drop_index("ix_referrals_referrer_id", table_name="referrals")
    op.drop_table("referrals")