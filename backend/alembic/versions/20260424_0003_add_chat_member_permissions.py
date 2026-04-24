"""add chat member permissions

Revision ID: 20260424_0003
Revises: 20260424_0002
Create Date: 2026-04-24 19:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0003"
down_revision = "20260424_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_members",
        sa.Column("can_send_messages", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("chat_members", "can_send_messages", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_members", "can_send_messages")
