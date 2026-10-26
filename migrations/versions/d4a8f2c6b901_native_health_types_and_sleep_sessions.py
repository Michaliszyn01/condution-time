"""native Health Connect types and multiple sleep sessions

Revision ID: d4a8f2c6b901
Revises: c7d2e9a4f1b3
Create Date: 2026-07-29 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "d4a8f2c6b901"
down_revision = "c7d2e9a4f1b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("training_records") as batch:
        batch.add_column(sa.Column("manual_training_type", sa.String(length=40)))
        batch.add_column(sa.Column("vo2_max", sa.Float()))

    with op.batch_alter_table("sleep_records") as batch:
        batch.drop_constraint("uq_sleep_record_date", type_="unique")
        batch.add_column(sa.Column("maximum_heart_rate", sa.Float()))
        batch.add_column(
            sa.Column(
                "is_primary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade():
    # Bancos com cochilos não podem voltar à unicidade sem perda. Mantemos o
    # downgrade explícito e seguro: ele só funciona quando há uma sessão/dia.
    with op.batch_alter_table("sleep_records") as batch:
        batch.drop_column("is_primary")
        batch.drop_column("maximum_heart_rate")
        batch.create_unique_constraint("uq_sleep_record_date", ["record_date"])

    with op.batch_alter_table("training_records") as batch:
        batch.drop_column("vo2_max")
        batch.drop_column("manual_training_type")
