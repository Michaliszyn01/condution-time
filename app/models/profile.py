from app.extensions import db
from app.models.base import TimestampMixin


class StudySubjectProgress(TimestampMixin, db.Model):
    __tablename__ = "study_subject_progress"

    subject_name = db.Column(
        db.String(80, collation="NOCASE"),
        nullable=False,
        unique=True,
    )
    level = db.Column(db.Integer, nullable=False, default=1)
    xp = db.Column(db.Integer, nullable=False, default=0)
    total_minutes = db.Column(db.Integer, nullable=False, default=0)
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    correct_questions = db.Column(db.Integer, nullable=False, default=0)
    sessions_count = db.Column(db.Integer, nullable=False, default=0)
    last_studied_at = db.Column(db.DateTime(timezone=True))


class UserProfile(TimestampMixin, db.Model):
    __tablename__ = "user_profile"

    name = db.Column(db.String(120), nullable=False, default="Usuário")
    avatar_initials = db.Column(db.String(4))
    birth_date = db.Column(db.Date)
    height_cm = db.Column(db.Float)
    academic_goal = db.Column(db.String(500))
    physical_goal = db.Column(db.String(500))
    weekly_study_minutes = db.Column(db.Integer)
    weekly_training_count = db.Column(db.Integer)
    sleep_target_minutes = db.Column(db.Integer)
    hydration_target_ml = db.Column(db.Integer)
    hydration_reminders_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )


class ExperienceEvent(TimestampMixin, db.Model):
    __tablename__ = "experience_events"
    __table_args__ = (
        db.UniqueConstraint("event_key", name="uq_experience_event_key"),
        db.CheckConstraint("xp_amount >= 0", name="ck_experience_xp_nonnegative"),
    )

    event_key = db.Column(db.String(180), nullable=False, unique=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    source_type = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.Integer)
    xp_amount = db.Column(db.Integer, nullable=False)
    earned_at = db.Column(db.DateTime(timezone=True), nullable=False)
    record_date = db.Column(db.Date, nullable=False, index=True)
    metadata_json = db.Column(db.Text)


class AchievementUnlock(TimestampMixin, db.Model):
    __tablename__ = "achievement_unlocks"

    achievement_key = db.Column(db.String(100), nullable=False, unique=True)
    unlocked_at = db.Column(db.DateTime(timezone=True), nullable=False)
    progress_value = db.Column(db.Integer, nullable=False, default=0)
