"""Add deal details fields and manager commission

Revision ID: 008_deal_details_commission
Revises: 007_add_delete_deal_audit
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_deal_details_commission"
down_revision: Union[str, None] = "007_add_delete_deal_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotency guard)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    """Add deal detail fields, commission_rate, manager_commission."""
    # detected_deals — new nullable columns
    for col_name, col_type in [
        ("notes", sa.Text()),
        ("target_sell_price", sa.Numeric(12, 2)),
        ("seller_condition", sa.String(500)),
        ("seller_city", sa.String(100)),
        ("seller_specs", sa.String(500)),
        ("seller_phone", sa.String(50)),
        ("buyer_phone", sa.String(50)),
    ]:
        if not _col_exists("detected_deals", col_name):
            op.add_column("detected_deals", sa.Column(col_name, col_type, nullable=True))

    # users — commission_rate
    if not _col_exists("users", "commission_rate"):
        op.add_column("users", sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True, server_default="0.10"))

    # ledger — manager_commission
    if not _col_exists("ledger", "manager_commission"):
        op.add_column("ledger", sa.Column("manager_commission", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    """Remove added columns."""
    op.drop_column("ledger", "manager_commission")
    op.drop_column("users", "commission_rate")
    op.drop_column("detected_deals", "buyer_phone")
    op.drop_column("detected_deals", "seller_phone")
    op.drop_column("detected_deals", "seller_specs")
    op.drop_column("detected_deals", "seller_city")
    op.drop_column("detected_deals", "seller_condition")
    op.drop_column("detected_deals", "target_sell_price")
    op.drop_column("detected_deals", "notes")
