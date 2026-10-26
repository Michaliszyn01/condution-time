from app.extensions import db
from app.models.base import RecordMixin


class SessionRecord(RecordMixin, db.Model):
    __tablename__ = "session_records"
    __table_args__ = (
        db.CheckConstraint(
            "target_duration_minutes IS NULL OR target_duration_minutes > 0",
            name="ck_session_target_duration_positive",
        ),
        db.CheckConstraint(
            "actual_duration_seconds IS NULL OR actual_duration_seconds >= 0",
            name="ck_session_actual_duration_nonnegative",
        ),
        db.CheckConstraint(
            "self_rating IS NULL OR (self_rating >= 1 AND self_rating <= 10)",
            name="ck_session_self_rating_range",
        ),
        db.CheckConstraint(
            "focus_percentage IS NULL OR "
            "(focus_percentage >= 0 AND focus_percentage <= 100)",
            name="ck_session_focus_percentage_range",
        ),
    )

    session_type = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    related_category = db.Column(db.String(20), nullable=False)
    target_duration_minutes = db.Column(db.Integer)
    actual_duration_seconds = db.Column(db.Integer)
    computer_monitoring_enabled = db.Column(db.Boolean, nullable=False, default=False)
    objective_text = db.Column(db.String(2000))
    result_text = db.Column(db.String(2000))
    learned_text = db.Column(db.String(2000))
    difficulty_text = db.Column(db.String(2000))
    self_rating = db.Column(db.Integer)
    focus_percentage = db.Column(db.Integer)
    productive_seconds = db.Column(db.Integer)
    distracted_seconds = db.Column(db.Integer)
    status = db.Column(db.String(20), nullable=False, default="configured")
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
