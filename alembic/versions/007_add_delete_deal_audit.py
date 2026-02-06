"""Add delete_deal to auditaction enum

Revision ID: 007_add_delete_deal_audit
Revises: 006_fix_negotiation_stages
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_add_delete_deal_audit"
down_revision: Union[str, None] = "006_fix_negotiation_stages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add delete_deal to auditaction enum."""
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'delete_deal'")


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL."""
    pass
