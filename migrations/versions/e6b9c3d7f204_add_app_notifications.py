"""add app notifications

Revision ID: e6b9c3d7f204
Revises: d4a8f2c6b901
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "e6b9c3d7f204"
down_revision = "d4a8f2c6b901"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_notifications",
        sa.Column("notification_key", sa.String(length=180), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("action_url", sa.String(length=300), nullable=True),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default="info",
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=60), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_app_notification_severity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_key",
            name="uq_app_notification_key",
        ),
    )
    with op.batch_alter_table("app_notifications") as batch:
        batch.create_index(
            "ix_app_notifications_type",
            ["type"],
            unique=False,
        )
        batch.create_index(
            "ix_app_notifications_is_read",
            ["is_read"],
            unique=False,
        )
        batch.create_index(
            "ix_app_notifications_expires_at",
            ["expires_at"],
            unique=False,
        )
    with op.batch_alter_table("user_profile") as batch:
        batch.add_column(
            sa.Column(
                "hydration_reminders_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade():
    with op.batch_alter_table("user_profile") as batch:
        batch.drop_column("hydration_reminders_enabled")
    with op.batch_alter_table("app_notifications") as batch:
        batch.drop_index("ix_app_notifications_expires_at")
        batch.drop_index("ix_app_notifications_is_read")
        batch.drop_index("ix_app_notifications_type")
    op.drop_table("app_notifications")
