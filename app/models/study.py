from app.extensions import db
from app.models.base import RecordMixin


class StudyRecord(RecordMixin, db.Model):
    __tablename__ = "study_records"
    __table_args__ = (
        db.CheckConstraint("duration_minutes > 0", name="ck_study_duration_positive"),
        db.CheckConstraint(
            "questions_count IS NULL OR questions_count >= 0",
            name="ck_study_questions_nonnegative",
        ),
        db.CheckConstraint(
            "correct_answers IS NULL OR correct_answers >= 0",
            name="ck_study_correct_nonnegative",
        ),
        db.CheckConstraint(
            "correct_answers IS NULL OR questions_count IS NOT NULL",
            name="ck_study_correct_requires_questions",
        ),
        db.CheckConstraint(
            "correct_answers IS NULL OR correct_answers <= questions_count",
            name="ck_study_correct_within_questions",
        ),
    )

    subject = db.Column(db.String(80), nullable=False)
    topic = db.Column(db.String(150), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    questions_count = db.Column(db.Integer)
    correct_answers = db.Column(db.Integer)
    focus_quality = db.Column(db.String(20), nullable=False)
    learned_text = db.Column(db.String(2000))
    difficulty_text = db.Column(db.String(2000))
    record_origin = db.Column(db.String(30), nullable=False)
