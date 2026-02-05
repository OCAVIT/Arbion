"""Add target column to negotiation_messages table

Revision ID: 005_add_message_target
Revises: 004_add_raw_messages_chat_title
Create Date: 2026-02-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_message_target"
down_revision: Union[str, None] = "004_add_raw_messages_chat_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add target column to negotiation_messages and messagetarget enum."""
    # Create the enum type
    messagetarget = sa.Enum("seller", "buyer", name="messagetarget")
    messagetarget.create(op.get_bind(), checkfirst=True)

    # Add the column with default 'seller' for existing messages
    op.add_column(
        "negotiation_messages",
        sa.Column(
            "target",
            messagetarget,
            nullable=False,
            server_default="seller",
            comment="Which chat this message belongs to (seller or buyer)"
        )
    )

    # Also add 'buyer' to the messagerole enum if it doesn't exist
    op.execute("ALTER TYPE messagerole ADD VALUE IF NOT EXISTS 'buyer'")


def downgrade() -> None:
    """Remove target column from negotiation_messages."""
    op.drop_column("negotiation_messages", "target")

    # Drop the enum type
    messagetarget = sa.Enum("seller", "buyer", name="messagetarget")
    messagetarget.drop(op.get_bind(), checkfirst=True)
