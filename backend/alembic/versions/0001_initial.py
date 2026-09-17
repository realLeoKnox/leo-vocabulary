"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("sources",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False), sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "source_type", "source_date", name="uq_source_identity"))
    op.create_index("ix_sources_name", "sources", ["name"])
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_table("words",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word", sa.String(120), nullable=False),
        sa.Column("lemma", sa.String(120), nullable=False), sa.Column("phonetic", sa.String(160), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False), sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("lemma"))
    for name in ("word", "lemma", "priority", "created_at"):
        op.create_index(f"ix_words_{name}", "words", [name])
    op.create_table("meanings",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("pos", sa.String(30), nullable=False), sa.Column("zh", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("word_id", "pos", "zh", name="uq_meaning"))
    op.create_index("ix_meanings_word_id", "meanings", ["word_id"])
    op.create_table("word_family_members",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("member", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("word_id", "member", name="uq_family_member"))
    op.create_index("ix_word_family_members_word_id", "word_family_members", ["word_id"])
    op.create_index("ix_word_family_members_member", "word_family_members", ["member"])
    op.create_table("encounters",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False), sa.Column("surface_form", sa.String(120), nullable=False),
        sa.Column("context", sa.Text(), nullable=True), sa.Column("note", sa.Text(), nullable=True),
        sa.Column("encountered_at", sa.Date(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"))
    for name in ("word_id", "source_id", "encountered_at"):
        op.create_index(f"ix_encounters_{name}", "encounters", [name])
    op.create_table("review_states",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False), sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False), sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False), sa.Column("mastery", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("word_id", "mode", name="uq_review_state_mode"))
    for name in ("word_id", "mode", "due_at"):
        op.create_index(f"ix_review_states_{name}", "review_states", [name])
    op.create_table("review_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False), sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"))
    for name in ("word_id", "mode", "reviewed_at"):
        op.create_index(f"ix_review_logs_{name}", "review_logs", [name])


def downgrade() -> None:
    for table in ("review_logs", "review_states", "encounters", "word_family_members", "meanings", "words", "sources"):
        op.drop_table(table)

