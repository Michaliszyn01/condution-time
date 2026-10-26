from app.extensions import db
from app.models.base import TimestampMixin, utc_now


HEALTH_IMPORT_STATUSES = (
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
)


class HealthImportRun(TimestampMixin, db.Model):
    __tablename__ = "health_import_runs"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','running','completed',"
            "'completed_with_warnings','failed')",
            name="ck_health_import_run_status",
        ),
    )

    source_filename = db.Column(db.String(255), nullable=False)
    source_hash = db.Column(db.String(64), nullable=False, index=True)
    source_modified_at = db.Column(db.DateTime(timezone=True))
    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    finished_at = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(30), nullable=False, default="pending")
    imported_count = db.Column(db.Integer, nullable=False, default=0)
    updated_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    error_count = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.String(2000))


class BodyMeasurement(TimestampMixin, db.Model):
    __tablename__ = "body_measurements"
    __table_args__ = (
        db.UniqueConstraint(
            "source_provider",
            "source_record_id",
            name="uq_body_measurement_source",
        ),
    )

    measured_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    weight_kg = db.Column(db.Float)
    body_fat_percentage = db.Column(db.Float)
    skeletal_muscle_kg = db.Column(db.Float)
    muscle_percentage = db.Column(db.Float)
    bmi = db.Column(db.Float)
    source_provider = db.Column(db.String(50), nullable=False)
    source_record_id = db.Column(db.String(160), nullable=False)
    source_hash = db.Column(db.String(64), nullable=False)
    origin = db.Column(db.String(30), nullable=False, default="health_connect")
    imported_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_source_update_at = db.Column(db.DateTime(timezone=True))


class DailyHealthSummary(db.Model):
    __tablename__ = "daily_health_summaries"

    record_date = db.Column(db.Date, primary_key=True)
    steps = db.Column(db.Integer)
    active_calories = db.Column(db.Float)
    total_calories = db.Column(db.Float)
    distance_meters = db.Column(db.Float)
    active_minutes = db.Column(db.Integer)
    resting_heart_rate = db.Column(db.Float)
    average_heart_rate = db.Column(db.Float)
    max_heart_rate = db.Column(db.Float)
    vo2_max = db.Column(db.Float)
    source_provider = db.Column(
        db.String(50),
        nullable=False,
        default="health_connect",
    )
    source_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

