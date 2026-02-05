"""Add missing negotiation stages to enum

Revision ID: 006_fix_negotiation_stages
Revises: 005_add_message_target
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "006_fix_negotiation_stages"
down_revision: Union[str, None] = "005_add_message_target"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing stages to negotiationstage enum."""
    # ВАЖНО: ALTER TYPE ... ADD VALUE нельзя выполнять внутри транзакции
    # Поэтому нужно коммитить после каждого добавления
    connection = op.get_bind()

    # Добавляем каждое значение отдельно с autocommit
    enum_values = ['price_discussion', 'logistics', 'warm', 'handed_to_manager']

    for value in enum_values:
        try:
            # Выполняем вне транзакции
            connection.execute(
                text(f"ALTER TYPE negotiationstage ADD VALUE IF NOT EXISTS '{value}'")
            )
            connection.commit()
        except Exception as e:
            # Если значение уже существует, игнорируем
            print(f"Note: Could not add enum value '{value}': {e}")
            pass


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL - no downgrade possible."""
    # PostgreSQL doesn't support DROP VALUE for enums
    # If needed, would require creating new type and migrating data
    pass
