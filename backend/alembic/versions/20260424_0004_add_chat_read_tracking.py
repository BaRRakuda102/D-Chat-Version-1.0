"""add chat read tracking

Revision ID: 20260424_0004
Revises: 20260424_0003
Create Date: 2026-04-24 19:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0004"
down_revision = "20260424_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_members",
        sa.Column("last_read_message_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_members_last_read_message_id",
        "chat_members",
        "chat_messages",
        ["last_read_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_chat_members_last_read_message_id", "chat_members", type_="foreignkey")
    op.drop_column("chat_members", "last_read_message_id")
