"""add health import, profile and private computer contexts

Revision ID: b8c1e4f7a9d2
Revises: 6b6e5d3f0e2a
Create Date: 2026-07-28 18:00:00
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


revision = "b8c1e4f7a9d2"
down_revision = "6b6e5d3f0e2a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "health_import_runs",
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_modified_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(length=2000)),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed',"
            "'completed_with_warnings','failed')",
            name="ck_health_import_run_status",
        ),
    )
    op.create_index(
        "ix_health_import_runs_source_hash",
        "health_import_runs",
        ["source_hash"],
    )
    op.create_table(
        "body_measurements",
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Float()),
        sa.Column("body_fat_percentage", sa.Float()),
        sa.Column("skeletal_muscle_kg", sa.Float()),
        sa.Column("muscle_percentage", sa.Float()),
        sa.Column("bmi", sa.Float()),
        sa.Column("source_provider", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=30), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_source_update_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_provider",
            "source_record_id",
            name="uq_body_measurement_source",
        ),
    )
    op.create_index(
        "ix_body_measurements_measured_at",
        "body_measurements",
        ["measured_at"],
    )
    op.create_table(
        "daily_health_summaries",
        sa.Column("record_date", sa.Date(), primary_key=True),
        sa.Column("steps", sa.Integer()),
        sa.Column("active_calories", sa.Float()),
        sa.Column("total_calories", sa.Float()),
        sa.Column("distance_meters", sa.Float()),
        sa.Column("active_minutes", sa.Integer()),
        sa.Column("resting_heart_rate", sa.Float()),
        sa.Column("average_heart_rate", sa.Float()),
        sa.Column("max_heart_rate", sa.Float()),
        sa.Column("vo2_max", sa.Float()),
        sa.Column("source_provider", sa.String(length=50), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "study_subject_progress",
        sa.Column("subject_name", sa.String(length=80, collation="NOCASE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("total_minutes", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_questions", sa.Integer(), nullable=False),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("last_studied_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("subject_name"),
    )
    op.create_table(
        "user_profile",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("birth_date", sa.Date()),
        sa.Column("height_cm", sa.Float()),
        sa.Column("academic_goal", sa.String(length=500)),
        sa.Column("physical_goal", sa.String(length=500)),
        sa.Column("weekly_study_minutes", sa.Integer()),
        sa.Column("weekly_training_count", sa.Integer()),
        sa.Column("sleep_target_minutes", sa.Integer()),
        sa.Column("hydration_target_ml", sa.Integer()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "project_rules",
        sa.Column(
            "project_key",
            sa.String(length=100, collation="NOCASE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("match_terms", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_project_rule_classification",
        ),
        sa.CheckConstraint(
            "category IN ('study','programming','work','communication',"
            "'entertainment','social','gaming','system','other')",
            name="ck_project_rule_category",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name="ck_project_rule_priority",
        ),
        sa.UniqueConstraint("project_key"),
    )
    now = datetime.now(timezone.utc)
    project_rules = sa.table(
        "project_rules",
        sa.column("project_key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("match_terms", sa.Text),
        sa.column("classification", sa.String),
        sa.column("category", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("priority", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        project_rules,
        [
            {
                "project_key": "condution_time",
                "display_name": "Condution Time",
                "match_terms": '["condution time","condutiontime"]',
                "classification": "productive",
                "category": "programming",
                "enabled": True,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
            },
            {
                "project_key": "routine_ia",
                "display_name": "Routine IA",
                "match_terms": '["routine ia","routineia"]',
                "classification": "productive",
                "category": "programming",
                "enabled": True,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
            },
            {
                "project_key": "orionxt",
                "display_name": "OrionXT",
                "match_terms": '["orionxt","orion xt"]',
                "classification": "productive",
                "category": "programming",
                "enabled": True,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    with op.batch_alter_table("sleep_records") as batch:
        batch.alter_column("perceived_quality", existing_type=sa.String(20), nullable=True)
        batch.alter_column("woke_restored", existing_type=sa.String(20), nullable=True)
        batch.add_column(sa.Column("sleep_started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("sleep_ended_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("sleep_stages_json", sa.Text()))
        batch.add_column(sa.Column("average_heart_rate", sa.Float()))
        batch.add_column(sa.Column("minimum_heart_rate", sa.Float()))
        batch.add_column(sa.Column("average_spo2", sa.Float()))
        batch.add_column(sa.Column("minimum_spo2", sa.Float()))
        batch.add_column(sa.Column("source_provider", sa.String(length=50)))
        batch.add_column(sa.Column("source_record_id", sa.String(length=160)))
        batch.add_column(sa.Column("source_hash", sa.String(length=64)))
        batch.add_column(sa.Column("imported_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_source_update_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint(
            "uq_sleep_source_record_id", ["source_record_id"]
        )
    with op.batch_alter_table("training_records") as batch:
        batch.alter_column("intensity", existing_type=sa.Integer(), nullable=True)
        batch.alter_column(
            "perceived_performance", existing_type=sa.String(20), nullable=True
        )
        batch.alter_column(
            "discomfort_level", existing_type=sa.String(20), nullable=True
        )
        batch.add_column(
            sa.Column(
                "record_origin",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )
        batch.add_column(sa.Column("training_started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("training_ended_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("distance_meters", sa.Float()))
        batch.add_column(sa.Column("calories", sa.Float()))
        batch.add_column(sa.Column("average_heart_rate", sa.Float()))
        batch.add_column(sa.Column("maximum_heart_rate", sa.Float()))
        batch.add_column(sa.Column("average_pace_seconds_per_km", sa.Float()))
        batch.add_column(sa.Column("average_speed_mps", sa.Float()))
        batch.add_column(sa.Column("steps", sa.Integer()))
        batch.add_column(sa.Column("segments_summary_json", sa.Text()))
        batch.add_column(sa.Column("source_provider", sa.String(length=50)))
        batch.add_column(sa.Column("source_record_id", sa.String(length=160)))
        batch.add_column(sa.Column("source_hash", sa.String(length=64)))
        batch.add_column(sa.Column("imported_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_source_update_at", sa.DateTime(timezone=True)))
        batch.create_unique_constraint(
            "uq_training_source_record_id", ["source_record_id"]
        )
    with op.batch_alter_table("computer_activity_blocks") as batch:
        batch.drop_constraint("ck_computer_block_source", type_="check")
        batch.create_check_constraint(
            "ck_computer_block_source",
            "classification_source IN "
            "('manual_rule','project_rule','site_allowlist',"
            "'default_rule','session_context','fallback')",
        )
        batch.add_column(sa.Column("project_rule_id", sa.Integer()))
        batch.add_column(sa.Column("project_key", sa.String(length=100)))
        batch.add_column(sa.Column("project_display_name", sa.String(length=150)))
        batch.add_column(sa.Column("site_key", sa.String(length=30)))
        batch.add_column(sa.Column("context_source", sa.String(length=30)))
        batch.create_foreign_key(
            "fk_computer_block_project_rule",
            "project_rules",
            ["project_rule_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_computer_activity_blocks_project_rule_id", ["project_rule_id"])
        batch.create_index("ix_computer_activity_blocks_project_key", ["project_key"])
        batch.create_index("ix_computer_activity_blocks_site_key", ["site_key"])


def downgrade():
    with op.batch_alter_table("computer_activity_blocks") as batch:
        batch.drop_constraint("ck_computer_block_source", type_="check")
        batch.create_check_constraint(
            "ck_computer_block_source",
            "classification_source IN "
            "('manual_rule','default_rule','session_context','fallback')",
        )
        batch.drop_index("ix_computer_activity_blocks_site_key")
        batch.drop_index("ix_computer_activity_blocks_project_key")
        batch.drop_index("ix_computer_activity_blocks_project_rule_id")
        batch.drop_constraint("fk_computer_block_project_rule", type_="foreignkey")
        for name in (
            "context_source",
            "site_key",
            "project_display_name",
            "project_key",
            "project_rule_id",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("training_records") as batch:
        batch.drop_constraint("uq_training_source_record_id", type_="unique")
        for name in (
            "last_source_update_at",
            "imported_at",
            "source_hash",
            "source_record_id",
            "source_provider",
            "segments_summary_json",
            "steps",
            "average_speed_mps",
            "average_pace_seconds_per_km",
            "maximum_heart_rate",
            "average_heart_rate",
            "calories",
            "distance_meters",
            "training_ended_at",
            "training_started_at",
            "record_origin",
        ):
            batch.drop_column(name)
        batch.alter_column("discomfort_level", existing_type=sa.String(20), nullable=False)
        batch.alter_column(
            "perceived_performance", existing_type=sa.String(20), nullable=False
        )
        batch.alter_column("intensity", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("sleep_records") as batch:
        batch.drop_constraint("uq_sleep_source_record_id", type_="unique")
        for name in (
            "last_source_update_at",
            "imported_at",
            "source_hash",
            "source_record_id",
            "source_provider",
            "minimum_spo2",
            "average_spo2",
            "minimum_heart_rate",
            "average_heart_rate",
            "sleep_stages_json",
            "sleep_ended_at",
            "sleep_started_at",
        ):
            batch.drop_column(name)
        # Existing imported rows can contain NULL subjective fields, so forcing
        # NOT NULL would be unsafe. Downgrade intentionally preserves nullable.
    op.drop_table("project_rules")
    op.drop_table("user_profile")
    op.drop_table("study_subject_progress")
    op.drop_table("daily_health_summaries")
    op.drop_index("ix_body_measurements_measured_at", table_name="body_measurements")
    op.drop_table("body_measurements")
    op.drop_index("ix_health_import_runs_source_hash", table_name="health_import_runs")
    op.drop_table("health_import_runs")
