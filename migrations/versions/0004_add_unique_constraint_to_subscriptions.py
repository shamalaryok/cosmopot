"""add unique constraint to subscriptions.user_id

Revision ID: 0004_add_unique_constraint_to_subscriptions
Revises: 0003_create_generation_tasks
Create Date: 2024-11-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_unique_constraint_to_subscriptions"
down_revision = "0003_create_generation_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_subscriptions_user_id",
            ["user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_subscriptions_user_id", type_="unique")
