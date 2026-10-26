"""add experience ledger and watch completion state

Revision ID: c7d2e9a4f1b3
Revises: b8c1e4f7a9d2
Create Date: 2026-07-28 21:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "c7d2e9a4f1b3"
down_revision = "b8c1e4f7a9d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_profile") as batch:
        batch.add_column(sa.Column("avatar_initials", sa.String(length=4)))
    with op.batch_alter_table("training_records") as batch:
        batch.add_column(sa.Column("source_exercise_type", sa.Integer()))
        batch.add_column(
            sa.Column(
                "suggestion_status",
                sa.String(length=20),
                nullable=False,
                server_default="available",
            )
        )
    with op.batch_alter_table("sleep_records") as batch:
        batch.add_column(
            sa.Column(
                "suggestion_status",
                sa.String(length=20),
                nullable=False,
                server_default="available",
            )
        )

    op.execute(
        "UPDATE training_records SET suggestion_status = "
        "CASE WHEN source_record_id IS NOT NULL "
        "AND (intensity IS NULL OR perceived_performance IS NULL "
        "OR discomfort_level IS NULL) THEN 'available' ELSE 'completed' END"
    )
    op.execute(
        "UPDATE sleep_records SET suggestion_status = "
        "CASE WHEN source_record_id IS NOT NULL "
        "AND (perceived_quality IS NULL OR woke_restored IS NULL) "
        "THEN 'available' ELSE 'completed' END"
    )

    op.create_table(
        "experience_events",
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer()),
        sa.Column("xp_amount", sa.Integer(), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "xp_amount >= 0",
            name="ck_experience_xp_nonnegative",
        ),
        sa.UniqueConstraint("event_key", name="uq_experience_event_key"),
    )
    op.create_index(
        "ix_experience_events_event_type",
        "experience_events",
        ["event_type"],
    )
    op.create_index(
        "ix_experience_events_record_date",
        "experience_events",
        ["record_date"],
    )
    op.create_table(
        "achievement_unlocks",
        sa.Column("achievement_key", sa.String(length=100), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("progress_value", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("achievement_key"),
    )


def downgrade():
    op.drop_table("achievement_unlocks")
    op.drop_index(
        "ix_experience_events_record_date",
        table_name="experience_events",
    )
    op.drop_index(
        "ix_experience_events_event_type",
        table_name="experience_events",
    )
    op.drop_table("experience_events")
    with op.batch_alter_table("sleep_records") as batch:
        batch.drop_column("suggestion_status")
    with op.batch_alter_table("training_records") as batch:
        batch.drop_column("suggestion_status")
        batch.drop_column("source_exercise_type")
    with op.batch_alter_table("user_profile") as batch:
        batch.drop_column("avatar_initials")
