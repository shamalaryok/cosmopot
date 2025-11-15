"""add descending index for latest prompt lookup

Revision ID: 0006_add_prompt_latest_index
Revises: 0005_add_prompts_version_and_missing_columns
Create Date: 2024-11-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_add_prompt_latest_index"
down_revision = "0005_add_prompts_version_and_missing_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_prompts_slug_version_desc ON prompts (slug, version DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_prompts_slug_version_desc")
