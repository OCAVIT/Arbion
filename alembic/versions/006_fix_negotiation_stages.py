"""Add missing negotiation stages to enum

Revision ID: 006_fix_negotiation_stages
Revises: 005_add_message_target
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_fix_negotiation_stages"
down_revision: Union[str, None] = "005_add_message_target"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing stages to negotiationstage enum."""
    # Add new enum values that are missing in the database
    # Note: PostgreSQL doesn't support removing enum values, only adding
    op.execute("ALTER TYPE negotiationstage ADD VALUE IF NOT EXISTS 'price_discussion'")
    op.execute("ALTER TYPE negotiationstage ADD VALUE IF NOT EXISTS 'logistics'")
    op.execute("ALTER TYPE negotiationstage ADD VALUE IF NOT EXISTS 'warm'")
    op.execute("ALTER TYPE negotiationstage ADD VALUE IF NOT EXISTS 'handed_to_manager'")


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL - no downgrade possible."""
    # PostgreSQL doesn't support DROP VALUE for enums
    # If needed, would require creating new type and migrating data
    pass
