"""Add media_type to negotiation_messages for photo/video/document support.

Revision ID: 013_add_media_type
Revises: 012_add_audit_actions
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013_add_media_type"
down_revision: Union[str, None] = "012_add_audit_actions"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotency guard)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    if not _col_exists("negotiation_messages", "media_type"):
        op.add_column(
            "negotiation_messages",
            sa.Column("media_type", sa.String(20), nullable=True),
        )


def downgrade() -> None:
    if _col_exists("negotiation_messages", "media_type"):
        op.drop_column("negotiation_messages", "media_type")
