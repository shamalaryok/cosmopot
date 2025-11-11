"""No-op initial migration.

Revision ID: 0001_initial
Revises:
Create Date: 2023-10-30 11:07:00
"""

from __future__ import annotations

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:  # pragma: no cover - migrations are executed externally
    pass


def downgrade() -> None:  # pragma: no cover - migrations are executed externally
    pass
