from flask import Blueprint, jsonify, request

from app.services.notification_service import (
    delete_notification,
    list_notifications,
    mark_all_read,
    mark_read,
    serialize_notification,
    unread_count,
)


notifications_api = Blueprint(
    "notifications_api",
    __name__,
    url_prefix="/api/notifications",
)


@notifications_api.get("")
def index():
    try:
        return jsonify(
            success=True,
            **list_notifications(
                status=request.args.get("status", "all"),
                notification_type=request.args.get("type") or None,
                page=request.args.get("page", 1, type=int),
                per_page=request.args.get("per_page", 20, type=int),
            ),
        )
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400


@notifications_api.get("/unread-count")
def unread():
    return jsonify(success=True, unread_count=unread_count())


@notifications_api.post("/<int:notification_id>/read")
def read(notification_id: int):
    try:
        item = mark_read(notification_id)
        return jsonify(
            success=True,
            notification=serialize_notification(item),
            unread_count=unread_count(),
        )
    except LookupError as exc:
        return jsonify(success=False, message=str(exc)), 404


@notifications_api.post("/read-all")
def read_all():
    return jsonify(
        success=True,
        updated=mark_all_read(),
        unread_count=unread_count(),
    )


@notifications_api.delete("/<int:notification_id>")
def delete(notification_id: int):
    try:
        delete_notification(notification_id)
        return jsonify(success=True, unread_count=unread_count())
    except LookupError as exc:
        return jsonify(success=False, message=str(exc)), 404
