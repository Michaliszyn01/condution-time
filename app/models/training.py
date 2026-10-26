from app.extensions import db
from app.models.base import RecordMixin


class TrainingRecord(RecordMixin, db.Model):
    __tablename__ = "training_records"
    __table_args__ = (
        db.CheckConstraint(
            "duration_minutes > 0",
            name="ck_training_duration_positive",
        ),
        db.CheckConstraint(
            "intensity >= 1 AND intensity <= 10",
            name="ck_training_intensity_range",
        ),
    )

    training_type = db.Column(db.String(20), nullable=False)
    activity_name = db.Column(db.String(150), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    intensity = db.Column(db.Integer)
    perceived_performance = db.Column(db.String(20))
    exercises_text = db.Column(db.String(2000))
    discomfort_level = db.Column(db.String(20))
    discomfort_location = db.Column(db.String(150))
    notes = db.Column(db.String(2000))
    record_origin = db.Column(db.String(20), nullable=False, default="manual")
    training_started_at = db.Column(db.DateTime(timezone=True))
    training_ended_at = db.Column(db.DateTime(timezone=True))
    distance_meters = db.Column(db.Float)
    calories = db.Column(db.Float)
    average_heart_rate = db.Column(db.Float)
    maximum_heart_rate = db.Column(db.Float)
    average_pace_seconds_per_km = db.Column(db.Float)
    average_speed_mps = db.Column(db.Float)
    vo2_max = db.Column(db.Float)
    steps = db.Column(db.Integer)
    segments_summary_json = db.Column(db.Text)
    source_provider = db.Column(db.String(50))
    source_record_id = db.Column(db.String(160), unique=True)
    source_hash = db.Column(db.String(64))
    imported_at = db.Column(db.DateTime(timezone=True))
    last_source_update_at = db.Column(db.DateTime(timezone=True))
    source_exercise_type = db.Column(db.Integer)
    manual_training_type = db.Column(db.String(40))
    suggestion_status = db.Column(db.String(20), nullable=False, default="available")
