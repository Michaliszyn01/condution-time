from app.extensions import db
from app.models.base import RecordMixin


class SleepRecord(RecordMixin, db.Model):
    __tablename__ = "sleep_records"
    __table_args__ = (
        db.CheckConstraint("duration_minutes > 0", name="ck_sleep_duration_positive"),
        db.CheckConstraint(
            "awakenings_count >= 0",
            name="ck_sleep_awakenings_nonnegative",
        ),
    )

    sleep_start = db.Column(db.Time, nullable=False)
    sleep_end = db.Column(db.Time, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    perceived_quality = db.Column(db.String(20))
    awakenings_count = db.Column(db.Integer, nullable=False, default=0)
    woke_restored = db.Column(db.String(20))
    notes = db.Column(db.String(2000))
    record_origin = db.Column(db.String(20), nullable=False, default="manual")
    sleep_started_at = db.Column(db.DateTime(timezone=True))
    sleep_ended_at = db.Column(db.DateTime(timezone=True))
    sleep_stages_json = db.Column(db.Text)
    average_heart_rate = db.Column(db.Float)
    minimum_heart_rate = db.Column(db.Float)
    maximum_heart_rate = db.Column(db.Float)
    average_spo2 = db.Column(db.Float)
    minimum_spo2 = db.Column(db.Float)
    is_primary = db.Column(db.Boolean, nullable=False, default=True)
    source_provider = db.Column(db.String(50))
    source_record_id = db.Column(db.String(160), unique=True)
    source_hash = db.Column(db.String(64))
    imported_at = db.Column(db.DateTime(timezone=True))
    last_source_update_at = db.Column(db.DateTime(timezone=True))
    suggestion_status = db.Column(db.String(20), nullable=False, default="available")
