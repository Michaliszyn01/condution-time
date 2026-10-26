from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models import AppNotification


ALLOWED_SEVERITIES = {"info", "success", "warning", "error"}
PAGE_SIZE = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_notification(
    *,
    notification_key: str,
    type: str,
    title: str,
    message: str,
    action_url: str | None = None,
    severity: str = "info",
    source_type: str | None = None,
    source_id: int | None = None,
    expires_at: datetime | None = None,
    commit: bool = True,
) -> tuple[AppNotification, bool]:
    existing = db.session.scalar(
        db.select(AppNotification).where(
            AppNotification.notification_key == notification_key
        )
    )
    if existing is not None:
        return existing, False
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError("Severidade de notificação inválida.")
    notification = AppNotification(
        notification_key=notification_key[:180],
        type=type[:60],
        title=title[:160],
        message=message[:500],
        action_url=action_url[:300] if action_url else None,
        severity=severity,
        source_type=source_type[:60] if source_type else None,
        source_id=source_id,
        expires_at=expires_at,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    current_app.logger.info(
        "Notificação criada: chave=%s tipo=%s.",
        notification.notification_key,
        notification.type,
    )
    return notification, True


def create_cooldown_notification(*, cooldown_minutes: int = 60, **values):
    bucket = int(_now().timestamp() // (cooldown_minutes * 60))
    values["notification_key"] = f"{values['notification_key']}:{bucket}"
    return create_notification(**values)


def _active_clause():
    return db.or_(
        AppNotification.expires_at.is_(None),
        AppNotification.expires_at > _now(),
    )


def serialize_notification(item: AppNotification) -> dict:
    return {
        "id": item.id,
        "notification_key": item.notification_key,
        "type": item.type,
        "title": item.title,
        "message": item.message,
        "action_url": item.action_url,
        "severity": item.severity,
        "is_read": item.is_read,
        "created_at": item.created_at.isoformat(),
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "relative_time": format_relative_time(item.created_at),
    }


def format_relative_time(value: datetime) -> str:
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    seconds = max(int((_now() - value).total_seconds()), 0)
    if seconds < 60:
        return "Agora"
    if seconds < 3600:
        return f"Há {seconds // 60} min"
    if seconds < 86400:
        return f"Há {seconds // 3600} h"
    if seconds < 172800:
        return "Ontem"
    return f"Há {seconds // 86400} dias"


def unread_count() -> int:
    return int(
        db.session.scalar(
            db.select(db.func.count(AppNotification.id)).where(
                AppNotification.is_read.is_(False),
                _active_clause(),
            )
        )
        or 0
    )


def list_notifications(
    *,
    status: str = "all",
    notification_type: str | None = None,
    page: int = 1,
    per_page: int = PAGE_SIZE,
) -> dict:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 50)
    filters = [_active_clause()]
    if status == "unread":
        filters.append(AppNotification.is_read.is_(False))
    elif status == "read":
        filters.append(AppNotification.is_read.is_(True))
    elif status != "all":
        raise ValueError("Filtro de leitura inválido.")
    if notification_type:
        filters.append(AppNotification.type == notification_type)
    base = db.select(AppNotification).where(*filters)
    total = int(
        db.session.scalar(
            db.select(db.func.count()).select_from(base.subquery())
        )
        or 0
    )
    items = list(
        db.session.scalars(
            base.order_by(
                AppNotification.created_at.desc(),
                AppNotification.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    return {
        "items": [serialize_notification(item) for item in items],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max((total + per_page - 1) // per_page, 1),
        "unread_count": unread_count(),
    }


def mark_read(notification_id: int) -> AppNotification:
    item = db.session.get(AppNotification, notification_id)
    if item is None:
        raise LookupError("Notificação não encontrada.")
    if not item.is_read:
        item.is_read = True
        item.read_at = _now()
        db.session.commit()
        current_app.logger.info(
            "Notificação marcada como lida: id=%s.",
            notification_id,
        )
    return item


def mark_all_read() -> int:
    items = list(
        db.session.scalars(
            db.select(AppNotification).where(
                AppNotification.is_read.is_(False),
                _active_clause(),
            )
        )
    )
    now = _now()
    for item in items:
        item.is_read = True
        item.read_at = now
    db.session.commit()
    return len(items)


def delete_notification(notification_id: int) -> None:
    item = db.session.get(AppNotification, notification_id)
    if item is None:
        raise LookupError("Notificação não encontrada.")
    db.session.delete(item)
    db.session.commit()


def resolve_notification(notification_key: str) -> bool:
    item = db.session.scalar(
        db.select(AppNotification).where(
            AppNotification.notification_key == notification_key
        )
    )
    if item is None or item.is_read:
        return False
    item.is_read = True
    item.read_at = _now()
    db.session.commit()
    return True
