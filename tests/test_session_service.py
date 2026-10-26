from datetime import timedelta

import pytest

from app.extensions import db
from app.models.base import utc_now
from app.services.analytics_utils import get_local_today
from app.services.home_service import get_home_page_data
from app.services.session_service import (
    InvalidSessionTransitionError,
    SessionValidationError,
    cancel_session,
    create_session,
    finish_session,
    get_active_session,
    get_bonus_details,
    pause_session,
    resume_session,
    serialize_session,
    update_session_summary,
)


def valid_payload(**overrides):
    payload = {
        "session_type": "study",
        "title": "Revisar geometria",
        "related_category": "study",
        "target_duration_minutes": 50,
        "computer_monitoring_enabled": False,
        "objective_text": "Resolver dez questões",
    }
    payload.update(overrides)
    return payload


def test_create_session_sets_server_owned_initial_state(app):
    with app.app_context():
        session = create_session(valid_payload())

        assert session.record_date == get_local_today()
        assert session.status == "running"
        assert session.started_at is not None
        assert session.actual_duration_seconds == 0
        assert session.productive_seconds == 0
        assert session.distracted_seconds == 0
        assert session.finished_at is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_type", "gaming"),
        ("related_category", "project"),
        ("target_duration_minutes", 0),
        ("target_duration_minutes", 1441),
        ("computer_monitoring_enabled", "yes"),
    ],
)
def test_create_session_rejects_invalid_fields(app, field, value):
    with app.app_context(), pytest.raises(SessionValidationError):
        create_session(valid_payload(**{field: value}))


def test_pause_resume_finish_and_summary_follow_state_machine(app):
    with app.app_context():
        session = create_session(valid_payload())
        paused = pause_session(session.id, {"actual_duration_seconds": 120})
        assert paused.status == "paused"
        assert paused.actual_duration_seconds == 120

        resumed = resume_session(session.id, {})
        assert resumed.status == "running"
        assert resumed.started_at is not None

        completed = finish_session(
            session.id,
            {
                "actual_duration_seconds": 180,
                "productive_seconds": 0,
                "distracted_seconds": 0,
                "focus_percentage": 80,
            },
        )
        assert completed.status == "completed"
        assert completed.finished_at is not None

        saved = update_session_summary(
            session.id,
            {
                "result_text": "Resolvi as questões.",
                "learned_text": "Revisei áreas.",
                "difficulty_text": "",
                "self_rating": "very_good",
            },
        )
        assert saved.self_rating == 8
        assert saved.result_text == "Resolvi as questões."
        session_bonus, daily_bonus = get_bonus_details(saved)
        assert session_bonus["score"] == 5
        assert daily_bonus["score"] == 5

        with pytest.raises(InvalidSessionTransitionError):
            resume_session(session.id, {})


def test_elapsed_time_cannot_decrease_or_exceed_24_hours(app):
    with app.app_context():
        session = create_session(valid_payload())
        pause_session(session.id, {"actual_duration_seconds": 30})

        with pytest.raises(SessionValidationError):
            cancel_session(session.id, {"actual_duration_seconds": 29})
        with pytest.raises(SessionValidationError):
            cancel_session(session.id, {"actual_duration_seconds": 86401})


def test_cancelled_session_has_no_bonus_and_is_not_active(app):
    with app.app_context():
        session = create_session(valid_payload())
        cancelled = cancel_session(session.id, {"actual_duration_seconds": 10})
        session_bonus, daily_bonus = get_bonus_details(cancelled)

        assert cancelled.status == "cancelled"
        assert session_bonus["score"] == 0
        assert daily_bonus["score"] == 0
        assert get_active_session() is None
        with pytest.raises(InvalidSessionTransitionError):
            finish_session(
                session.id,
                {
                    "actual_duration_seconds": 10,
                    "productive_seconds": 0,
                    "distracted_seconds": 0,
                },
            )


def test_recovery_returns_latest_active_today_and_computes_running_elapsed(app):
    with app.app_context():
        first = create_session(valid_payload(title="Primeira"))
        pause_session(first.id, {"actual_duration_seconds": 15})
        second = create_session(valid_payload(title="Mais recente"))
        second.started_at = utc_now() - timedelta(seconds=4)
        db.session.commit()

        recovered = get_active_session()
        serialized = serialize_session(recovered)

        assert recovered.id == second.id
        assert serialized["current_elapsed_seconds"] >= 4


def test_completed_session_appears_on_home_and_updates_official_bonus(app):
    with app.app_context():
        session = create_session(valid_payload(title="Sessão integrada"))
        finish_session(
            session.id,
            {
                "actual_duration_seconds": 60,
                "productive_seconds": 0,
                "distracted_seconds": 0,
                "focus_percentage": 90,
            },
        )
        update_session_summary(
            session.id,
            {
                "result_text": "Objetivo concluído",
                "learned_text": "Aprendizado",
                "difficulty_text": None,
                "self_rating": 10,
            },
        )
        home = get_home_page_data(get_local_today())

        assert home["score"]["bonus"] == 5
        assert any(
            item["text"] == "Concluiu a sessão Sessão integrada"
            for item in home["accomplishments"]
        )
