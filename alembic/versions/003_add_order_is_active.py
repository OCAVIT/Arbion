"""Add is_active column to orders table

Revision ID: 003_add_order_is_active
Revises: 002_add_buyer_fields
Create Date: 2026-02-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_order_is_active"
down_revision: Union[str, None] = "002_add_buyer_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active column to orders with default True."""
    op.add_column(
        "orders",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.create_index("ix_orders_is_active", "orders", ["is_active"])


def downgrade() -> None:
    """Remove is_active column from orders."""
    op.drop_index("ix_orders_is_active", table_name="orders")
    op.drop_column("orders", "is_active")
