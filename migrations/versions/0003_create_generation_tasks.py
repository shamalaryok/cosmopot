"""create generation tasks and prompts tables

Revision ID: 0003_create_generation_tasks
Revises: 0002_create_billing_domain
Create Date: 2024-10-30 14:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_create_generation_tasks"
down_revision = "0002_create_billing_domain"
branch_labels = None
depends_on = None

prompt_source = sa.Enum(
    "system",
    "user",
    "external",
    name="prompt_source",
    native_enum=False,
)
generation_task_status = sa.Enum(
    "pending",
    "queued",
    "running",
    "completed",
    "failed",
    "canceled",
    name="generation_task_status",
    native_enum=False,
)
generation_task_source = sa.Enum(
    "api",
    "scheduler",
    "workflow",
    name="generation_task_source",
    native_enum=False,
)


def upgrade() -> None:
    bigint_pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    op.create_table(
        "prompts",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source",
            prompt_source,
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column(
            "parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("preview_asset_url", sa.String(length=2048), nullable=True),
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
        sa.UniqueConstraint("slug", name="uq_prompts_slug"),
    )
    op.create_index("ix_prompts_slug", "prompts", ["slug"], unique=True)

    op.create_table(
        "generation_tasks",
        sa.Column("id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            generation_task_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "source",
            generation_task_source,
            nullable=False,
            server_default=sa.text("'api'"),
        ),
        sa.Column(
            "parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result_parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("input_asset_url", sa.String(length=2048), nullable=True),
        sa.Column("result_asset_url", sa.String(length=2048), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_generation_tasks_user_status",
        "generation_tasks",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_generation_tasks_prompt_id",
        "generation_tasks",
        ["prompt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_tasks_prompt_id", table_name="generation_tasks")
    op.drop_index("ix_generation_tasks_user_status", table_name="generation_tasks")
    op.drop_table("generation_tasks")

    op.drop_index("ix_prompts_slug", table_name="prompts")
    op.drop_table("prompts")

    prompt_source.drop(op.get_bind())
    generation_task_status.drop(op.get_bind())
    generation_task_source.drop(op.get_bind())
