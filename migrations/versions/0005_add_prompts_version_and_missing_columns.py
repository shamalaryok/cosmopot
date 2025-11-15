"""add version column to prompts table and missing columns

Revision ID: 0005_add_prompts_version_and_missing_columns
Revises: 0004_add_unique_constraint_to_subscriptions
Create Date: 2024-11-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_add_prompts_version_and_missing_columns"
down_revision = "0004_add_unique_constraint_to_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns using op.add_column directly for SQLite compatibility
    # Add category enum
    op.add_column(
        "prompts",
        sa.Column(
            "category",
            sa.Enum(
                "generic",
                "lips",
                "cheeks",
                "eyes",
                "eyebrows",
                "eyelashes",
                "hair",
                "skin",
                "face",
                "body",
                "background",
                "clothing",
                "accessories",
                "lighting",
                "composition",
                "style",
                "other",
                name="prompt_category",
                native_enum=False,
            ),
            nullable=False,
            server_default=sa.text("'generic'"),
        )
    )
    
    # Add version column
    op.add_column(
        "prompts",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # Add parameters_schema column
    op.add_column(
        "prompts",
        sa.Column(
            "parameters_schema",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        )
    )
    
    # Add is_active column
    op.add_column(
        "prompts",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Drop old unique constraint and index using batch mode for SQLite
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.drop_constraint("uq_prompts_slug", type_="unique")
        batch_op.drop_index("ix_prompts_slug")
    
    # Add new unique constraint on (slug, version)
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_prompts_slug_version",
            ["slug", "version"]
        )
    
    # Add new indexes
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_prompts_category",
            ["category"],
            unique=False,
        )
        batch_op.create_index(
            "ix_prompts_slug_active",
            ["slug", "is_active"],
            unique=False,
        )


def downgrade() -> None:
    # Drop new indexes
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.drop_index("ix_prompts_slug_active")
        batch_op.drop_index("ix_prompts_category")
    
    # Drop new unique constraint
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.drop_constraint("uq_prompts_slug_version", type_="unique")
    
    # Add back old unique constraint and index
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.create_index("ix_prompts_slug", ["slug"], unique=True)
        batch_op.create_unique_constraint("uq_prompts_slug", ["slug"])
    
    # Drop added columns using op.drop_column directly
    op.drop_column("prompts", "is_active")
    op.drop_column("prompts", "parameters_schema")
    op.drop_column("prompts", "version")
    op.drop_column("prompts", "category")