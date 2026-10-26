from app.extensions import db
from app.models.base import RecordMixin, TimestampMixin


CLASSIFICATIONS = ("productive", "distracting", "neutral", "ignored")
CATEGORIES = (
    "study",
    "programming",
    "work",
    "communication",
    "entertainment",
    "social",
    "gaming",
    "system",
    "other",
)
CLASSIFICATION_SOURCES = (
    "manual_rule",
    "project_rule",
    "site_allowlist",
    "default_rule",
    "session_context",
    "fallback",
)


class ComputerActivityBlock(RecordMixin, db.Model):
    __tablename__ = "computer_activity_blocks"
    __table_args__ = (
        db.CheckConstraint(
            "duration_seconds > 0",
            name="ck_computer_block_duration_positive",
        ),
        db.CheckConstraint(
            "ended_at > started_at",
            name="ck_computer_block_time_order",
        ),
        db.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_computer_block_classification",
        ),
        db.CheckConstraint(
            "category IN "
            "('study','programming','work','communication','entertainment',"
            "'social','gaming','system','other')",
            name="ck_computer_block_category",
        ),
        db.CheckConstraint(
            "classification_source IN "
            "('manual_rule','project_rule','site_allowlist',"
            "'default_rule','session_context','fallback')",
            name="ck_computer_block_source",
        ),
        db.CheckConstraint(
            "(was_idle = 1 AND executable_name IS NULL) OR "
            "(was_idle = 0 AND executable_name IS NOT NULL)",
            name="ck_computer_block_idle_executable",
        ),
    )

    executable_name = db.Column(db.String(255), index=True)
    friendly_name = db.Column(db.String(255))
    classification = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    classification_source = db.Column(db.String(30), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)
    was_idle = db.Column(db.Boolean, nullable=False, default=False)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("session_records.id", ondelete="SET NULL"),
        index=True,
    )
    session = db.relationship("SessionRecord", lazy="joined")
    project_rule_id = db.Column(
        db.Integer,
        db.ForeignKey("project_rules.id", ondelete="SET NULL"),
        index=True,
    )
    project_key = db.Column(db.String(100), index=True)
    project_display_name = db.Column(db.String(150))
    site_key = db.Column(db.String(30), index=True)
    context_source = db.Column(db.String(30))


class ApplicationRule(TimestampMixin, db.Model):
    __tablename__ = "application_rules"
    __table_args__ = (
        db.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_application_rule_classification",
        ),
        db.CheckConstraint(
            "category IN "
            "('study','programming','work','communication','entertainment',"
            "'social','gaming','system','other')",
            name="ck_application_rule_category",
        ),
        db.CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name="ck_application_rule_priority",
        ),
    )

    executable_name = db.Column(
        db.String(255, collation="NOCASE"),
        nullable=False,
        unique=True,
    )
    friendly_name = db.Column(db.String(255))
    classification = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    priority = db.Column(db.Integer, nullable=False, default=100)


class ProjectRule(TimestampMixin, db.Model):
    __tablename__ = "project_rules"
    __table_args__ = (
        db.CheckConstraint(
            "classification IN ('productive','distracting','neutral','ignored')",
            name="ck_project_rule_classification",
        ),
        db.CheckConstraint(
            "category IN "
            "('study','programming','work','communication','entertainment',"
            "'social','gaming','system','other')",
            name="ck_project_rule_category",
        ),
        db.CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name="ck_project_rule_priority",
        ),
    )

    project_key = db.Column(
        db.String(100, collation="NOCASE"),
        nullable=False,
        unique=True,
    )
    display_name = db.Column(db.String(150), nullable=False)
    match_terms = db.Column(db.Text, nullable=False)
    classification = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    priority = db.Column(db.Integer, nullable=False, default=100)
