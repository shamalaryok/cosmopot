"""Update generation_task_status enum to use completed instead of succeeded

Revision ID: 0009_update_generation_task_status_enum
Revises: 0008_add_stripe_payment_provider
Create Date: 2024-11-10 10:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_update_generation_task_status_enum"
down_revision = "0008_add_stripe_payment_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update all existing 'succeeded' values to 'completed'
    op.execute(
        "UPDATE generation_tasks SET status = 'completed' WHERE status = 'succeeded'"
    )

    # For PostgreSQL, we need to recreate the enum type
    # For SQLite (native_enum=False), it's just a string check, so the app-level change is sufficient
    # Since native_enum=False is used, we don't need to alter the enum type definition
    # The app will handle both 'completed' and 'succeeded' through the Python enum


def downgrade() -> None:
    # Revert completed back to succeeded
    op.execute(
        "UPDATE generation_tasks SET status = 'succeeded' WHERE status = 'completed'"
    )
