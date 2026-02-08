"""Add announcements table for admin-to-manager communications.

Revision ID: 016_add_announcements
Revises: 015_add_outbox_reply_to
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "016_add_announcements"
down_revision: Union[str, None] = "015_add_outbox_reply_to"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("announcements"):
        op.create_table(
            "announcements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("announcement_reads"):
        op.create_table(
            "announcement_reads",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "announcement_id",
                sa.Integer(),
                sa.ForeignKey("announcements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "read_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("announcement_id", "user_id", name="uq_announcement_user"),
        )


def downgrade() -> None:
    if _table_exists("announcement_reads"):
        op.drop_table("announcement_reads")
    if _table_exists("announcements"):
        op.drop_table("announcements")
