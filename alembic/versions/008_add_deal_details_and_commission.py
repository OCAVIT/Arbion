"""Add deal details fields and manager commission

Revision ID: 008_add_deal_details_and_commission
Revises: 007_add_delete_deal_audit
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_add_deal_details_and_commission"
down_revision: Union[str, None] = "007_add_delete_deal_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deal detail fields, commission_rate, manager_commission."""
    # detected_deals — new nullable columns
    op.add_column("detected_deals", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("detected_deals", sa.Column("target_sell_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("detected_deals", sa.Column("seller_condition", sa.String(500), nullable=True))
    op.add_column("detected_deals", sa.Column("seller_city", sa.String(100), nullable=True))
    op.add_column("detected_deals", sa.Column("seller_specs", sa.String(500), nullable=True))
    op.add_column("detected_deals", sa.Column("seller_phone", sa.String(50), nullable=True))
    op.add_column("detected_deals", sa.Column("buyer_phone", sa.String(50), nullable=True))

    # users — commission_rate
    op.add_column("users", sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True, server_default="0.10"))

    # ledger — manager_commission
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
