"""add stripe payment provider support

Revision ID: 0008_add_stripe_payment_provider
Revises: add_analytics_tables
Create Date: 2024-11-06 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_add_stripe_payment_provider"
down_revision = "add_analytics_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    payment_provider = sa.Enum(
        "yookassa",
        "stripe",
        name="payment_provider",
        native_enum=False,
    )
    op.add_column(
        "payments",
        sa.Column(
            "provider",
            payment_provider,
            nullable=False,
            server_default=sa.text("'yookassa'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("payments", "provider")
