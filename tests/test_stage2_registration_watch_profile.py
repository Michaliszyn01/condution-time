from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import (
    AchievementUnlock,
    ComputerActivityBlock,
    ExperienceEvent,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
    UserProfile,
)
from app.health_import.mapper import map_training
from zoneinfo import ZoneInfo
from app.services.analytics_utils import get_local_today
from app.services.catalog_service import (
    exercise_catalog_item,
    subject_catalog_item,
)
from app.services.experience_service import (
    get_achievements,
    get_experience_summary,
)
from app.services.sleep_service import get_sleep_page_data
from app.services.study_service import build_study_page_data


def _study_payload(record_date):
    return {
        "record_date": record_date.isoformat(),
        "subject": "Matemática",
        "topic": "Revisão",
        "duration_minutes": 30,
        "questions_count": 10,
        "correct_answers": 8,
        "focus_quality": "Boa",
        "learned_text": "",
        "difficulty_text": "",
        "record_origin": "Estudo manual",
    }


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        ("/api/records/study", _study_payload),
        (
            "/api/records/training",
            lambda day: {
                "record_date": day.isoformat(),
                "training_type": "running",
                "activity_name": "Corrida",
                "duration_minutes": 30,
                "intensity": 6,
                "perceived_performance": "Bom",
                "exercises_text": "",
                "discomfort_level": "Nenhum",
                "discomfort_location": "",
                "notes": "",
            },
        ),
        (
            "/api/records/sleep",
            lambda day: {
                "record_date": day.isoformat(),
                "sleep_start": "23:00",
                "sleep_end": "07:00",
                "perceived_quality": "Boa",
                "awakenings_count": 1,
                "woke_restored": "Sim",
                "notes": "",
                "record_origin": "Manual",
            },
        ),
        (
            "/api/records/meal",
            lambda day: {
                "record_date": day.isoformat(),
                "meal_type": "Almoço",
                "meal_time": "12:00",
                "foods_text": "Alimento registrado",
                "approximate_amount": "",
                "has_protein": "Sim",
                "has_fruits_or_vegetables": "Sim",
                "perceived_quality": "Boa",
                "notes": "",
            },
        ),
        (
            "/api/records/hydration",
            lambda day: {
                "record_date": day.isoformat(),
                "amount": 200,
                "unit": "ml",
                "consumed_at": "12:00",
                "notes": "",
            },
        ),
    ],
)
def test_all_compatible_records_block_future_dates(client, app, endpoint, payload):
    with app.app_context():
        future = get_local_today() + timedelta(days=1)
    response = client.post(endpoint, json=payload(future))
    assert response.status_code == 400
    assert "futura" in response.get_json()["errors"]["record_date"]


def test_previous_day_study_updates_history_not_today(client, app):
    with app.app_context():
        today = get_local_today()
    previous = today - timedelta(days=1)
    response = client.post("/api/records/study", json=_study_payload(previous))
    assert response.status_code == 201
    assert response.get_json()["record"]["record_date"] == previous.isoformat()
    today_counts = client.get(f"/api/records/counts?date={today.isoformat()}").get_json()
    previous_counts = client.get(
        f"/api/records/counts?date={previous.isoformat()}"
    ).get_json()
    assert today_counts["counts"]["study"] == 0
    assert previous_counts["counts"]["study"] == 1
    assert "Revisão" in client.get("/historico").text


def test_watch_training_is_completed_in_place_without_duplicate(client, app):
    with app.app_context():
        record = TrainingRecord(
            record_date=get_local_today() - timedelta(days=1),
            training_type="rowing",
            activity_name="Remo",
            duration_minutes=45,
            intensity=None,
            perceived_performance=None,
            discomfort_level=None,
            record_origin="health_connect",
            source_provider="health_connect",
            source_record_id="watch-training-1",
            source_hash="a" * 64,
            source_exercise_type=53,
            suggestion_status="available",
            distance_meters=5000,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id
    suggestions = client.get("/api/records/watch/training").get_json()["records"]
    assert suggestions[0]["training_type_label"] == "Caminhada"
    response = client.patch(
        f"/api/records/watch/training/{record_id}",
        json={
            "intensity": 7,
            "perceived_performance": "Bom",
            "exercises_text": "Séries registradas",
            "discomfort_level": "Nenhum",
            "discomfort_location": "",
            "notes": "Percepção manual",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(TrainingRecord.id))) == 1
        merged = db.session.get(TrainingRecord, record_id)
        assert merged.distance_meters == 5000
        assert merged.record_origin == "merged"
        assert merged.suggestion_status == "completed"
        assert merged.notes == "Percepção manual"


def test_watch_sleep_is_completed_in_place_without_duplicate(client, app):
    with app.app_context():
        day = get_local_today() - timedelta(days=1)
        record = SleepRecord(
            record_date=day,
            sleep_start=datetime.strptime("23:00", "%H:%M").time(),
            sleep_end=datetime.strptime("07:00", "%H:%M").time(),
            duration_minutes=480,
            awakenings_count=2,
            perceived_quality=None,
            woke_restored=None,
            record_origin="health_connect",
            source_provider="health_connect",
            source_record_id="watch-sleep-1",
            source_hash="b" * 64,
            suggestion_status="available",
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id
    response = client.patch(
        f"/api/records/watch/sleep/{record_id}",
        json={
            "perceived_quality": "Boa",
            "woke_restored": "Parcialmente",
            "notes": "Percepção preservada",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(SleepRecord.id))) == 1
        merged = db.session.get(SleepRecord, record_id)
        assert merged.awakenings_count == 2
        assert merged.record_origin == "merged"
        assert merged.perceived_quality == "good"


def test_quick_hydration_uses_server_time_and_updates_total(client):
    assert client.post(
        "/api/records/hydration/quick",
        json={"amount_ml": 200},
    ).status_code == 201
    assert client.post(
        "/api/records/hydration/quick",
        json={"amount_ml": 300},
    ).status_code == 201
    assert client.get("/api/records/hydration/today").get_json()["total_ml"] == 500


def test_real_health_connect_codes_and_subject_colors_are_centralized():
    assert exercise_catalog_item(code=58)["display_name"] == "Outro treino"
    assert exercise_catalog_item(code=53)["training_key"] == "walking"
    assert exercise_catalog_item(code=33)["display_name"] == "Corrida"
    assert exercise_catalog_item(code=34)["display_name"] == "Corrida na esteira"
    assert exercise_catalog_item(code=49)["display_name"] == "Natação em piscina"
    assert exercise_catalog_item(code=999)["recognized"] is False
    mathematics = subject_catalog_item("Matemática")
    assert mathematics["subject_key"] == "matematica"
    assert mathematics["color_key"] == "blue"
    assert subject_catalog_item("Matéria nova")["subject_key"] == "other"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (58, "other"),
        (53, "walking"),
        (33, "running"),
        (34, "treadmill"),
        (49, "swimming"),
    ],
)
def test_mapper_uses_codes_found_in_real_archive(code, expected):
    class Reader:
        timezone = ZoneInfo("America/Sao_Paulo")

        def overlapping_sum(self, *args):
            return None

        def series_stats(self, *args):
            return {}

        def segments_for(self, *args):
            return []

    mapped = map_training(
        {
            "row_id": 1,
            "uuid": f"real-{code}".encode(),
            "last_modified_time": 1_720_003_600_000,
            "start_time": 1_720_000_000_000,
            "end_time": 1_720_003_600_000,
            "exercise_type": code,
            "title": None,
        },
        Reader(),
    )
    assert mapped["training_type"] == expected
    assert mapped["source_exercise_type"] == code


def test_study_chart_is_stacked_by_subject_and_calendar_filters(client, app):
    with app.app_context():
        day = get_local_today() - timedelta(days=2)
        db.session.add_all(
            [
                StudyRecord(
                    record_date=day,
                    subject="Matemática",
                    topic="A",
                    duration_minutes=50,
                    focus_quality="good",
                    record_origin="manual",
                ),
                StudyRecord(
                    record_date=day,
                    subject="História",
                    topic="B",
                    duration_minutes=30,
                    focus_quality="good",
                    record_origin="manual",
                ),
            ]
        )
        db.session.commit()
        data = build_study_page_data(day)
    datasets = {item["label"]: item["data"] for item in data["weekly"]["datasets"]}
    assert datasets["Matemática"][-1] == 50
    assert datasets["História"][-1] == 30
    response = client.get(f"/estudo?date={day.isoformat()}")
    assert response.status_code == 200
    assert day.isoformat() in response.text
    assert "Data selecionada" in response.text


def test_sleep_stages_use_real_types_without_forced_sum(client, app):
    with app.app_context():
        day = get_local_today()
        stages = [
            {
                "type": 1,
                "start": "2026-07-28T02:00:00+00:00",
                "end": "2026-07-28T02:10:00+00:00",
            },
            {
                "type": 4,
                "start": "2026-07-28T02:10:00+00:00",
                "end": "2026-07-28T03:10:00+00:00",
            },
            {
                "type": 5,
                "start": "2026-07-28T03:10:00+00:00",
                "end": "2026-07-28T03:40:00+00:00",
            },
            {
                "type": 6,
                "start": "2026-07-28T03:40:00+00:00",
                "end": "2026-07-28T04:20:00+00:00",
            },
        ]
        db.session.add(
            SleepRecord(
                record_date=day,
                sleep_start=datetime.strptime("23:00", "%H:%M").time(),
                sleep_end=datetime.strptime("07:00", "%H:%M").time(),
                duration_minutes=480,
                awakenings_count=1,
                record_origin="health_connect",
                sleep_stages_json=json.dumps(stages),
                suggestion_status="available",
            )
        )
        db.session.commit()
        data = get_sleep_page_data(day)
    totals = {item["key"]: item["minutes"] for item in data["sleep_stages"]["items"]}
    assert totals == {"awake": 10, "light": 60, "deep": 30, "rem": 40}
    response = client.get(f"/sono?date={day.isoformat()}")
    assert "Sono REM" in response.text
    assert "não força uma soma artificial" in response.text


def test_computer_total_excludes_idle_and_keeps_current_status(client, app):
    with app.app_context():
        day = get_local_today() - timedelta(days=1)
        common = {
            "record_date": day,
            "started_at": datetime.now(timezone.utc),
            "ended_at": datetime.now(timezone.utc),
            "executable_name": "test.exe",
            "friendly_name": "Teste",
            "category": "other",
            "classification_source": "manual_rule",
            "was_idle": False,
        }
        db.session.add_all(
            [
                ComputerActivityBlock(
                    **common,
                    duration_seconds=100,
                    classification="productive",
                ),
                ComputerActivityBlock(
                    **common,
                    duration_seconds=200,
                    classification="distracting",
                ),
                ComputerActivityBlock(
                    **common,
                    duration_seconds=300,
                    classification="neutral",
                ),
                ComputerActivityBlock(
                    **{
                        **common,
                        "was_idle": True,
                        "executable_name": None,
                        "friendly_name": None,
                        "classification_source": "fallback",
                    },
                    duration_seconds=400,
                    classification="neutral",
                ),
            ]
        )
        db.session.commit()
    response = client.get(f"/computador?date={day.isoformat()}")
    assert response.status_code == 200
    assert "Tempo total no computador" in response.text
    assert "10 min" in response.text
    assert "Tempo ocioso" in response.text
    assert "Você está visualizando" in response.text


def test_profile_name_fallback_edit_and_header_are_database_driven(client, app):
    assert "Usuário" in client.get("/").text
    response = client.patch(
        "/api/profile",
        json={"name": "Marcos Eduardo", "avatar_initials": "ME"},
    )
    assert response.status_code == 200
    page = client.get("/perfil")
    assert "Marcos Eduardo" in page.text
    assert ">ME<" in page.text
    with app.app_context():
        assert db.session.scalar(db.select(UserProfile)).name == "Marcos Eduardo"


def test_xp_ledger_is_recalculable_deduplicated_and_daily_capped(app):
    with app.app_context():
        day = get_local_today()
        for index in range(6):
            db.session.add(
                StudyRecord(
                    record_date=day,
                    subject="Matemática",
                    topic=f"Tópico {index}",
                    duration_minutes=30,
                    focus_quality="good",
                    record_origin="manual",
                )
            )
        db.session.commit()
        first = get_experience_summary()
        second = get_experience_summary()
        study_xp = int(
            db.session.scalar(
                db.select(db.func.sum(ExperienceEvent.xp_amount)).where(
                    ExperienceEvent.event_type == "study_record"
                )
            )
            or 0
        )
        event_count = int(
            db.session.scalar(db.select(db.func.count(ExperienceEvent.id)))
            or 0
        )
        assert study_xp == 25
        assert first == second
        get_experience_summary()
        assert db.session.scalar(db.select(db.func.count(ExperienceEvent.id))) == event_count
        assert first["level"] >= 1
        assert first["next_level_xp"] == 100 + (first["level"] - 1) * 50


def test_achievement_unlock_is_idempotent(app):
    with app.app_context():
        db.session.add(
            StudyRecord(
                record_date=get_local_today(),
                subject="Matemática",
                topic="Primeiro",
                duration_minutes=30,
                focus_quality="good",
                record_origin="manual",
            )
        )
        db.session.commit()
        first = get_achievements()
        second = get_achievements()
        assert next(item for item in first if item["achievement_key"] == "study_first")[
            "unlocked"
        ]
        assert first == second
        assert (
            db.session.scalar(
                db.select(db.func.count(AchievementUnlock.id)).where(
                    AchievementUnlock.achievement_key == "study_first"
                )
            )
            == 1
        )
