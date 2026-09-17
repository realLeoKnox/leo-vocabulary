"""add stable identities and extensible learning event fields

Revision ID: 0002
Revises: 0001
"""
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _add_and_fill_uid(table: str) -> None:
    op.add_column(table, sa.Column("uid", sa.String(36), nullable=True))
    connection = op.get_bind()
    ids = connection.execute(sa.text(f"SELECT id FROM {table}")).scalars().all()
    for row_id in ids:
        connection.execute(sa.text(f"UPDATE {table} SET uid = :uid WHERE id = :id"), {"uid": str(uuid4()), "id": row_id})
    with op.batch_alter_table(table) as batch:
        batch.alter_column("uid", existing_type=sa.String(36), nullable=False)
        batch.create_index(f"ix_{table}_uid", ["uid"], unique=True)


def upgrade() -> None:
    for table in ("sources", "words", "encounters", "review_logs"):
        _add_and_fill_uid(table)

    now = datetime.now(timezone.utc)
    with op.batch_alter_table("encounters") as batch:
        batch.add_column(sa.Column("origin", sa.String(40), nullable=True))
        batch.add_column(sa.Column("familiarity", sa.String(20), nullable=True))
        batch.add_column(sa.Column("marked_unknown", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("first_marked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("token_index", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("char_offset", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("external_ref", sa.String(200), nullable=True))
        batch.add_column(sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE encounters SET origin = 'json_import', marked_unknown = 1, occurred_at = created_at"))
    with op.batch_alter_table("encounters") as batch:
        batch.alter_column("origin", existing_type=sa.String(40), nullable=False)
        batch.alter_column("marked_unknown", existing_type=sa.Boolean(), nullable=False)
        batch.alter_column("occurred_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_index("ix_encounters_origin", ["origin"])
        batch.create_index("ix_encounters_familiarity", ["familiarity"])
        batch.create_index("ix_encounters_marked_unknown", ["marked_unknown"])
        batch.create_index("ix_encounters_external_ref", ["external_ref"])
        batch.create_index("ix_encounters_occurred_at", ["occurred_at"])

    with op.batch_alter_table("review_logs") as batch:
        batch.add_column(sa.Column("mastery_before", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("mastery_after", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("interval_before", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("interval_after", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("response_time_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("encounter_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("context", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_review_logs_encounter", "encounters", ["encounter_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_review_logs_encounter_id", ["encounter_id"])
    op.execute(sa.text(
        "UPDATE review_logs SET mastery_before = 0, mastery_after = 0, interval_before = 0, interval_after = 0"
    ))
    with op.batch_alter_table("review_logs") as batch:
        for column in ("mastery_before", "mastery_after", "interval_before", "interval_after"):
            batch.alter_column(column, existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("review_logs") as batch:
        batch.drop_index("ix_review_logs_encounter_id")
        batch.drop_constraint("fk_review_logs_encounter", type_="foreignkey")
        for column in ("context", "encounter_id", "response_time_ms", "next_review_at", "interval_after",
                       "interval_before", "mastery_after", "mastery_before"):
            batch.drop_column(column)
    with op.batch_alter_table("encounters") as batch:
        for index in ("ix_encounters_occurred_at", "ix_encounters_external_ref", "ix_encounters_marked_unknown",
                      "ix_encounters_familiarity", "ix_encounters_origin"):
            batch.drop_index(index)
        for column in ("occurred_at", "external_ref", "char_offset", "token_index", "first_marked_at",
                       "marked_unknown", "familiarity", "origin"):
            batch.drop_column(column)
    for table in ("review_logs", "encounters", "words", "sources"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_uid")
            batch.drop_column("uid")
