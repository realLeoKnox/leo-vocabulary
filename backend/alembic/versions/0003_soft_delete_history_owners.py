"""archive vocabulary and sources instead of deleting history

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_sources_archived_at", ["archived_at"])
    with op.batch_alter_table("words") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_words_archived_at", ["archived_at"])


def downgrade() -> None:
    with op.batch_alter_table("words") as batch:
        batch.drop_index("ix_words_archived_at")
        batch.drop_column("archived_at")
    with op.batch_alter_table("sources") as batch:
        batch.drop_index("ix_sources_archived_at")
        batch.drop_column("archived_at")
