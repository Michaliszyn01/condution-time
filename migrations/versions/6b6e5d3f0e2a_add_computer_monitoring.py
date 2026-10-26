"""add computer monitoring

Revision ID: 6b6e5d3f0e2a
Revises: 24f24f837fe5
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "6b6e5d3f0e2a"
down_revision = "24f24f837fe5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_rules",
        sa.Column("executable_name", sa.String(255, collation="NOCASE"), nullable=False),
        sa.Column("friendly_name", sa.String(255), nullable=True),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_application_rule_classification",
        ),
        sa.CheckConstraint(
            "category IN ('study','programming','work','communication',"
            "'entertainment','social','gaming','system','other')",
            name="ck_application_rule_category",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name="ck_application_rule_priority",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("executable_name"),
    )
    op.create_table(
        "computer_activity_blocks",
        sa.Column("executable_name", sa.String(255), nullable=True),
        sa.Column("friendly_name", sa.String(255), nullable=True),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("classification_source", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("was_idle", sa.Boolean(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "duration_seconds > 0",
            name="ck_computer_block_duration_positive",
        ),
        sa.CheckConstraint(
            "ended_at > started_at",
            name="ck_computer_block_time_order",
        ),
        sa.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_computer_block_classification",
        ),
        sa.CheckConstraint(
            "category IN ('study','programming','work','communication',"
            "'entertainment','social','gaming','system','other')",
            name="ck_computer_block_category",
        ),
        sa.CheckConstraint(
            "classification_source IN "
            "('manual_rule','default_rule','session_context','fallback')",
            name="ck_computer_block_source",
        ),
        sa.CheckConstraint(
            "(was_idle = 1 AND executable_name IS NULL) OR "
            "(was_idle = 0 AND executable_name IS NOT NULL)",
            name="ck_computer_block_idle_executable",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session_records.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("computer_activity_blocks") as batch_op:
        batch_op.create_index(
            "ix_computer_activity_blocks_executable_name",
            ["executable_name"],
        )
        batch_op.create_index(
            "ix_computer_activity_blocks_record_date",
            ["record_date"],
        )
        batch_op.create_index(
            "ix_computer_activity_blocks_session_id",
            ["session_id"],
        )
        batch_op.create_index(
            "ix_computer_activity_blocks_started_at",
            ["started_at"],
        )


def downgrade():
    op.drop_table("computer_activity_blocks")
    op.drop_table("application_rules")
