from datetime import date

from flask import Blueprint, jsonify, request

from app.services.session_service import (
    InvalidSessionTransitionError,
    SessionNotFoundError,
    SessionPersistenceError,
    SessionValidationError,
    cancel_session,
    create_session,
    finish_session,
    get_active_session,
    get_bonus_details,
    get_session,
    pause_session,
    resume_session,
    serialize_session,
    update_session_summary,
)


sessions_api = Blueprint("sessions_api", __name__, url_prefix="/api/sessions")


def _payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise SessionValidationError({"_schema": "Envie um objeto JSON válido."})
    return payload


def _success(session, message: str, status_code: int = 200):
    session_bonus, daily_bonus = get_bonus_details(session)
    return (
        jsonify(
            {
                "success": True,
                "message": message,
                "session": serialize_session(session),
                "session_bonus": session_bonus,
                "daily_session_bonus": daily_bonus,
            }
        ),
        status_code,
    )


def _handle(action, message: str, status_code: int = 200):
    try:
        return _success(action(), message, status_code)
    except SessionValidationError as exc:
        return jsonify(
            success=False,
            message="Revise os dados informados.",
            errors=exc.errors,
        ), 400
    except SessionNotFoundError:
        return jsonify(
            success=False,
            message="Sessão não encontrada.",
            errors={},
        ), 404
    except InvalidSessionTransitionError as exc:
        return jsonify(success=False, message=str(exc), errors={}), 409
    except SessionPersistenceError:
        return jsonify(
            success=False,
            message="Não foi possível salvar a sessão. Tente novamente.",
            errors={},
        ), 500


@sessions_api.post("")
def create():
    return _handle(lambda: create_session(_payload()), "Sessão iniciada.", 201)


@sessions_api.get("/active")
def active():
    raw_date = request.args.get("date")
    try:
        reference_date = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        return jsonify(
            success=False,
            message="Data inválida.",
            errors={"date": "Use o formato AAAA-MM-DD."},
        ), 400
    session = get_active_session(reference_date)
    return jsonify(
        success=True,
        active_session=serialize_session(session) if session else None,
    )


@sessions_api.get("/<int:session_id>")
def detail(session_id: int):
    return _handle(lambda: get_session(session_id), "Sessão carregada.")


@sessions_api.post("/<int:session_id>/pause")
def pause(session_id: int):
    return _handle(
        lambda: pause_session(session_id, _payload()),
        "Sessão pausada.",
    )


@sessions_api.post("/<int:session_id>/resume")
def resume(session_id: int):
    return _handle(
        lambda: resume_session(session_id, _payload()),
        "Sessão retomada.",
    )


@sessions_api.post("/<int:session_id>/finish")
def finish(session_id: int):
    return _handle(
        lambda: finish_session(session_id, _payload()),
        "Sessão finalizada.",
    )


@sessions_api.post("/<int:session_id>/cancel")
def cancel(session_id: int):
    return _handle(
        lambda: cancel_session(session_id, _payload()),
        "Sessão cancelada.",
    )


@sessions_api.patch("/<int:session_id>/summary")
def summary(session_id: int):
    return _handle(
        lambda: update_session_summary(session_id, _payload()),
        "Resumo salvo.",
    )
