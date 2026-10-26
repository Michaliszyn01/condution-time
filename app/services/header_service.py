from flask import current_app

from app.extensions import db
from app.models import UserProfile
from app.services.hydration_service import get_today_hydration
from app.services.notification_service import list_notifications
from app.services.profile_service import get_user_identity


def get_header_state() -> dict:
    profile = db.session.scalar(db.select(UserProfile).limit(1))
    notifications = list_notifications(per_page=5)
    return {
        "profile": get_user_identity(profile),
        "hydration": get_today_hydration(profile),
        "notifications": notifications,
        "unread_notifications_count": notifications["unread_count"],
        "desktop": {
            "available": bool(
                current_app.config.get("DESKTOP_MODE")
                and current_app.config.get("DESKTOP_BRIDGE")
            )
        },
    }
