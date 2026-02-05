"""Add last_active_at column to users

Revision ID: 001_add_last_active_at
Revises: 000_initial_schema
Create Date: 2026-02-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_add_last_active_at"
down_revision: Union[str, None] = "000_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_active_at column to users table."""
    op.add_column(
        "users",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove last_active_at column from users table."""
    op.drop_column("users", "last_active_at")
