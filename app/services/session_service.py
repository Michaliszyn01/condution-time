from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import SessionRecord
from app.models.base import utc_now
from app.services.analytics_utils import get_local_today
from app.services.scoring_service import calculate_session_bonus


MAX_SESSION_SECONDS = 24 * 60 * 60
SESSION_TYPES = {
    "study": {"label": "Estudo", "icon": "book-open", "category": "study", "category_label": "Estudo"},
    "programming": {"label": "Programação", "icon": "code-2", "category": "computer", "category_label": "Uso do computador"},
    "work": {"label": "Trabalho", "icon": "briefcase", "category": "work", "category_label": "Trabalho"},
    "reading": {"label": "Leitura", "icon": "book", "category": "study", "category_label": "Estudo"},
    "project": {"label": "Projeto", "icon": "folder-kanban", "category": "project", "category_label": "Projetos"},
    "other": {"label": "Outro", "icon": "shapes", "category": "other", "category_label": "Outro"},
}
RELATED_CATEGORIES = {"study", "computer", "project", "work", "other"}
ACTIVE_STATUSES = {"running", "paused"}
SUMMARY_FIELDS = {"result_text", "learned_text", "difficulty_text", "self_rating"}
RATING_VALUES = {
    "bad": 2,
    "regular": 4,
    "good": 6,
    "very_good": 8,
    "excellent": 10,
}
RATING_LABELS = {
    2: "Ruim",
    4: "Regular",
    6: "Boa",
    8: "Muito boa",
    10: "Excelente",
}


class SessionValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Dados de sessão inválidos.")
        self.errors = errors


class SessionNotFoundError(LookupError):
    pass


class InvalidSessionTransitionError(RuntimeError):
    pass


class SessionPersistenceError(RuntimeError):
    pass


def _commit() -> None:
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise SessionPersistenceError from exc


def _text(
    payload: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    maximum: int = 2000,
) -> str | None:
    value = payload.get(field)
    if value is None:
        if required:
            raise SessionValidationError({field: "Este campo é obrigatório."})
        return None
    if not isinstance(value, str):
        raise SessionValidationError({field: "Informe um texto válido."})
    value = value.strip()
    if required and not value:
        raise SessionValidationError({field: "Este campo é obrigatório."})
    if len(value) > maximum:
        raise SessionValidationError(
            {field: f"Use no máximo {maximum} caracteres."}
        )
    return value or None


def _integer(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
    required: bool = True,
) -> int | None:
    value = payload.get(field)
    if value is None and not required:
        return None
    if isinstance(value, bool):
        raise SessionValidationError({field: "Informe um número inteiro válido."})
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SessionValidationError({field: "Informe um número inteiro válido."})
    if parsed < minimum or parsed > maximum:
        raise SessionValidationError(
            {field: f"Informe um valor entre {minimum} e {maximum}."}
        )
    return parsed


def _ensure_known_fields(payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SessionValidationError(
            {"_schema": f"Campos não permitidos: {', '.join(unknown)}."}
        )


def get_session(session_id: int) -> SessionRecord:
    session = db.session.get(SessionRecord, session_id)
    if session is None:
        raise SessionNotFoundError("Sessão não encontrada.")
    return session


def create_session(payload: dict[str, Any]) -> SessionRecord:
    allowed = {
        "session_type",
        "title",
        "related_category",
        "target_duration_minutes",
        "computer_monitoring_enabled",
        "objective_text",
    }
    _ensure_known_fields(payload, allowed)
    session_type = payload.get("session_type")
    if session_type not in SESSION_TYPES:
        raise SessionValidationError(
            {"session_type": "Selecione um tipo de sessão válido."}
        )
    related_category = payload.get("related_category")
    expected_category = SESSION_TYPES[session_type]["category"]
    if related_category not in RELATED_CATEGORIES or related_category != expected_category:
        raise SessionValidationError(
            {"related_category": "A categoria não corresponde ao tipo selecionado."}
        )
    monitoring = payload.get("computer_monitoring_enabled", False)
    if not isinstance(monitoring, bool):
        raise SessionValidationError(
            {"computer_monitoring_enabled": "Informe verdadeiro ou falso."}
        )

    session = SessionRecord(
        record_date=get_local_today(),
        session_type=session_type,
        title=_text(payload, "title", required=True, maximum=150),
        related_category=related_category,
        target_duration_minutes=_integer(
            payload,
            "target_duration_minutes",
            minimum=1,
            maximum=1440,
        ),
        computer_monitoring_enabled=monitoring,
        objective_text=_text(payload, "objective_text"),
        actual_duration_seconds=0,
        productive_seconds=0,
        distracted_seconds=0,
        status="running",
        started_at=utc_now(),
    )
    db.session.add(session)
    _commit()
    return session


def get_active_session(reference_date: date | None = None) -> SessionRecord | None:
    target_date = reference_date or get_local_today()
    return db.session.scalar(
        db.select(SessionRecord)
        .where(
            SessionRecord.record_date == target_date,
            SessionRecord.status.in_(ACTIVE_STATUSES),
        )
        .order_by(SessionRecord.created_at.desc(), SessionRecord.id.desc())
        .limit(1)
    )


def _elapsed(payload: dict[str, Any], session: SessionRecord) -> int:
    value = _integer(
        payload,
        "actual_duration_seconds",
        minimum=0,
        maximum=MAX_SESSION_SECONDS,
    )
    persisted = int(session.actual_duration_seconds or 0)
    if value < persisted:
        raise SessionValidationError(
            {
                "actual_duration_seconds": (
                    "O tempo total não pode ser menor que o já registrado."
                )
            }
        )
    return value


def _require_status(session: SessionRecord, allowed: set[str], action: str) -> None:
    if session.status not in allowed:
        raise InvalidSessionTransitionError(
            f"Não é possível {action} uma sessão com status {session.status}."
        )


def pause_session(session_id: int, payload: dict[str, Any]) -> SessionRecord:
    _ensure_known_fields(payload, {"actual_duration_seconds"})
    session = get_session(session_id)
    _require_status(session, {"running"}, "pausar")
    session.actual_duration_seconds = _elapsed(payload, session)
    session.status = "paused"
    _commit()
    return session


def resume_session(session_id: int, payload: dict[str, Any]) -> SessionRecord:
    _ensure_known_fields(payload, set())
    session = get_session(session_id)
    _require_status(session, {"paused"}, "continuar")
    session.status = "running"
    session.started_at = utc_now()
    _commit()
    return session


def finish_session(session_id: int, payload: dict[str, Any]) -> SessionRecord:
    allowed = {
        "actual_duration_seconds",
        "focus_percentage",
        "productive_seconds",
        "distracted_seconds",
    }
    _ensure_known_fields(payload, allowed)
    session = get_session(session_id)
    _require_status(session, ACTIVE_STATUSES, "finalizar")
    elapsed = _elapsed(payload, session)
    productive = _integer(
        payload, "productive_seconds", minimum=0, maximum=MAX_SESSION_SECONDS, required=False
    )
    distracted = _integer(
        payload, "distracted_seconds", minimum=0, maximum=MAX_SESSION_SECONDS, required=False
    )
    productive = int(session.productive_seconds or 0) if productive is None else productive
    distracted = int(session.distracted_seconds or 0) if distracted is None else distracted
    if productive + distracted > elapsed:
        raise SessionValidationError(
            {"metrics": "Os tempos produtivo e distraído não podem superar o tempo total."}
        )

    session.actual_duration_seconds = elapsed
    session.focus_percentage = _integer(
        payload, "focus_percentage", minimum=0, maximum=100, required=False
    )
    session.productive_seconds = productive
    session.distracted_seconds = distracted
    session.status = "completed"
    session.finished_at = utc_now()
    _commit()
    return session


def cancel_session(session_id: int, payload: dict[str, Any]) -> SessionRecord:
    _ensure_known_fields(payload, {"actual_duration_seconds"})
    session = get_session(session_id)
    _require_status(session, ACTIVE_STATUSES, "cancelar")
    session.actual_duration_seconds = _elapsed(payload, session)
    session.status = "cancelled"
    session.finished_at = utc_now()
    _commit()
    return session


def update_session_summary(session_id: int, payload: dict[str, Any]) -> SessionRecord:
    _ensure_known_fields(payload, SUMMARY_FIELDS)
    session = get_session(session_id)
    _require_status(session, {"completed"}, "editar o resumo de")

    for field in ("result_text", "learned_text", "difficulty_text"):
        if field in payload:
            setattr(session, field, _text(payload, field))
    if "self_rating" in payload:
        rating = payload["self_rating"]
        if isinstance(rating, str) and rating in RATING_VALUES:
            rating = RATING_VALUES[rating]
        session.self_rating = _integer(
            {"self_rating": rating},
            "self_rating",
            minimum=1,
            maximum=10,
            required=False,
        )
    _commit()
    return session


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def current_elapsed_seconds(session: SessionRecord) -> int:
    persisted = max(0, int(session.actual_duration_seconds or 0))
    if session.status != "running" or session.started_at is None:
        return persisted
    started_at = _as_utc(session.started_at)
    segment = max(0, int((utc_now() - started_at).total_seconds()))
    return min(MAX_SESSION_SECONDS, persisted + segment)


def get_bonus_details(session: SessionRecord) -> tuple[dict[str, Any], dict[str, Any]]:
    session_result = calculate_session_bonus([session])
    session_detail = session_result["sessions"][0]
    day_sessions = list(
        db.session.scalars(
            db.select(SessionRecord)
            .where(SessionRecord.record_date == session.record_date)
            .order_by(SessionRecord.id)
        )
    )
    daily_detail = calculate_session_bonus(day_sessions)
    return session_detail, daily_detail


def serialize_session(session: SessionRecord) -> dict[str, Any]:
    type_data = SESSION_TYPES.get(session.session_type, {})
    return {
        "id": session.id,
        "record_date": session.record_date.isoformat(),
        "session_type": session.session_type,
        "session_type_label": type_data.get("label", session.session_type),
        "title": session.title,
        "related_category": session.related_category,
        "related_category_label": type_data.get(
            "category_label", session.related_category
        ),
        "target_duration_minutes": session.target_duration_minutes,
        "actual_duration_seconds": int(session.actual_duration_seconds or 0),
        "current_elapsed_seconds": current_elapsed_seconds(session),
        "computer_monitoring_enabled": bool(session.computer_monitoring_enabled),
        "objective_text": session.objective_text,
        "result_text": session.result_text,
        "learned_text": session.learned_text,
        "difficulty_text": session.difficulty_text,
        "self_rating": session.self_rating,
        "self_rating_label": RATING_LABELS.get(session.self_rating),
        "focus_percentage": session.focus_percentage,
        "productive_seconds": int(session.productive_seconds or 0),
        "distracted_seconds": int(session.distracted_seconds or 0),
        "status": session.status,
        "started_at": _as_utc(session.started_at).isoformat()
        if session.started_at
        else None,
        "finished_at": _as_utc(session.finished_at).isoformat()
        if session.finished_at
        else None,
    }


def get_session_page_data() -> dict[str, Any]:
    active = get_active_session()
    return {
        "options": {
            "types": [
                {"value": value, **metadata}
                for value, metadata in SESSION_TYPES.items()
            ],
            "durations": [25, 50, 60, 90],
            "default_type": "study",
            "default_duration": 50,
        },
        "active_session": serialize_session(active) if active else None,
    }
