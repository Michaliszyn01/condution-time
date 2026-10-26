from app.extensions import db
from app.models.base import TimestampMixin


class AppNotification(TimestampMixin, db.Model):
    __tablename__ = "app_notifications"
    __table_args__ = (
        db.UniqueConstraint(
            "notification_key",
            name="uq_app_notification_key",
        ),
        db.CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_app_notification_severity",
        ),
    )

    notification_key = db.Column(db.String(180), nullable=False, unique=True)
    type = db.Column(db.String(60), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    action_url = db.Column(db.String(300))
    severity = db.Column(db.String(16), nullable=False, default="info")
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    read_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True), index=True)
    source_type = db.Column(db.String(60))
    source_id = db.Column(db.Integer)
