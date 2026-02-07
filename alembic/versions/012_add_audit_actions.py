"""Add new audit action enum values: send_draft, skip_lead, create_lead, update_payment.

Revision ID: 012_add_audit_actions
Revises: 011_strategic_update
Create Date: 2026-02-07

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_audit_actions"
down_revision: Union[str, None] = "011_strategic_update"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'send_draft'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'skip_lead'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'create_lead'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'update_payment'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums
    pass
