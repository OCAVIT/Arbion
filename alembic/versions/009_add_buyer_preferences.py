"""Add buyer_preferences to detected_deals

Revision ID: 009_buyer_preferences
Revises: 008_deal_details_commission
Create Date: 2026-02-07

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009_buyer_preferences"
down_revision: Union[str, None] = "008_deal_details_commission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotency guard)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    if not _col_exists("detected_deals", "buyer_preferences"):
        op.add_column(
            "detected_deals",
            sa.Column("buyer_preferences", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("detected_deals", "buyer_preferences")
