import json
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.extensions import db
from app.health_import.mapper import _energy_kcal, grouped_awakenings
from app.health_import.repository import HealthImportRepository
from app.models import SleepRecord, StudyRecord, TrainingRecord
from app.services.analytics_utils import get_local_today
from app.services.catalog_service import PLATFORM_EXERCISE_SESSION_TYPES
from app.services.sleep_service import get_sleep_page_data
from app.services.study_service import build_study_page_data
from app.services.training_service import get_training_page_data
from app.services.watch_service import sleep_stage_data


@pytest.mark.parametrize(
    ("code", "label"),
    [
        (58, "Outro treino"),
        (53, "Caminhada"),
        (33, "Corrida"),
        (34, "Corrida na esteira"),
        (49, "Natação em piscina"),
    ],
)
def test_platform_exercise_session_types_match_native_api(code, label):
    assert PLATFORM_EXERCISE_SESSION_TYPES[code][1] == label


def test_native_energy_is_normalized_to_kilocalories():
    assert _energy_kcal(211_487) == 211.49
    assert _energy_kcal(350) == 350


@pytest.mark.parametrize("route", ["/estudo", "/treino", "/sono", "/computador"])
def test_category_date_control_is_compact_and_calendar_keeps_query(client, route):
    today_response = client.get(route)
    assert today_response.status_code == 200
    assert 'class="date-navigation card"' not in today_response.text
    assert 'class="date-context-compact"' not in today_response.text

    selected = get_local_today() - timedelta(days=2)
    response = client.get(f"{route}?date={selected.isoformat()}")
    assert response.status_code == 200
    assert 'class="date-context-compact"' in response.text
    assert "Voltar para hoje" in response.text
    assert f'data-calendar-date="{selected.isoformat()}"' in response.text
    assert "is-highlighted" in response.text


def test_empty_selected_days_are_not_evaluated_or_negative(app):
    selected = get_local_today() - timedelta(days=3)
    with app.app_context():
        study = build_study_page_data(selected)
        training = get_training_page_data(selected)
        sleep = get_sleep_page_data(selected)
    for data in (study, training, sleep):
        assert data["score"]["evaluated"] is False
        assert data["score"]["comparison_tone"] == "neutral"
        assert data["score"]["comparison"] == "Sem avaliação nesta data"


def _training_payload(*, source_id="native-58", code=58):
    start = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    return {
        "record_date": date(2026, 7, 27),
        "training_type": PLATFORM_EXERCISE_SESSION_TYPES[code][0],
        "source_exercise_type": code,
        "activity_name": PLATFORM_EXERCISE_SESSION_TYPES[code][1],
        "training_started_at": start,
        "training_ended_at": start + timedelta(minutes=45),
        "duration_minutes": 45,
        "distance_meters": 1000,
        "calories": 200,
        "average_heart_rate": 120,
        "maximum_heart_rate": 150,
        "average_pace_seconds_per_km": 2700,
        "average_speed_mps": 0.37,
        "vo2_max": None,
        "steps": 1000,
        "segments_summary_json": "[]",
        "source_record_id": source_id,
        "last_source_update_at": start,
        "source_hash": f"{code:064d}",
    }


def test_old_import_is_reclassified_without_duplication(app):
    with app.app_context():
        record = TrainingRecord(
            record_date=date(2026, 7, 27),
            training_type="sailing",
            activity_name="Vela",
            duration_minutes=45,
            record_origin="health_connect",
            source_provider="health_connect",
            source_record_id="native-58",
            source_hash="old",
            source_exercise_type=58,
        )
        db.session.add(record)
        db.session.commit()
        HealthImportRepository().upsert_training(_training_payload())
        db.session.commit()
        rows = list(db.session.scalars(db.select(TrainingRecord)))
        assert len(rows) == 1
        assert rows[0].training_type == "other"
        assert rows[0].activity_name == "Outro treino"
        assert rows[0].source_exercise_type == 58


def test_manual_training_classification_is_preserved(app):
    with app.app_context():
        record = TrainingRecord(
            record_date=date(2026, 7, 27),
            training_type="strength",
            manual_training_type="strength",
            activity_name="Treino de força",
            duration_minutes=45,
            record_origin="merged",
            source_provider="health_connect",
            source_record_id="native-58",
            source_hash="old",
            source_exercise_type=58,
        )
        db.session.add(record)
        db.session.commit()
        HealthImportRepository().upsert_training(_training_payload())
        db.session.commit()
        assert record.manual_training_type == "strength"
        assert record.activity_name == "Treino de força"
        assert record.source_exercise_type == 58


def test_awakenings_ignore_edges_and_group_close_fragments():
    def stage(kind, start, end):
        return {
            "type": kind,
            "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        }

    stages = [
        stage(1, 0, 60),
        stage(1, 600, 690),
        stage(7, 720, 810),
        stage(1, 1800, 1950),
        stage(1, 3540, 3600),
    ]
    assert grouped_awakenings(
        stages,
        session_start_ms=0,
        session_end_ms=3_600_000,
    ) == 2


def test_sleep_stages_keep_raw_types_and_summarize_awake(app):
    stages = [
        {"type": 1, "start": "2026-07-27T22:00:00+00:00", "end": "2026-07-27T22:10:00+00:00"},
        {"type": 3, "start": "2026-07-27T22:10:00+00:00", "end": "2026-07-27T22:15:00+00:00"},
        {"type": 7, "start": "2026-07-27T22:15:00+00:00", "end": "2026-07-27T22:20:00+00:00"},
        {"type": 4, "start": "2026-07-27T22:20:00+00:00", "end": "2026-07-27T23:20:00+00:00"},
        {"type": 5, "start": "2026-07-27T23:20:00+00:00", "end": "2026-07-28T00:20:00+00:00"},
        {"type": 6, "start": "2026-07-28T00:20:00+00:00", "end": "2026-07-28T01:20:00+00:00"},
    ]
    record = SleepRecord(
        record_date=date(2026, 7, 28),
        sleep_start=time(19),
        sleep_end=time(22, 20),
        duration_minutes=200,
        awakenings_count=1,
        sleep_stages_json=json.dumps(stages),
    )
    with app.app_context():
        result = sleep_stage_data(record)
    assert {item["key"]: item["minutes"] for item in result["items"]} == {
        "awake": 20,
        "light": 60,
        "deep": 60,
        "rem": 60,
    }
    assert {item["key"] for item in result["timeline"]} >= {
        "awake",
        "awake_in_bed",
        "out_of_bed",
    }
    assert result["efficiency_percent"] == 90


def test_sleep_page_distinguishes_primary_sleep_and_nap(app):
    selected = get_local_today() - timedelta(days=1)
    with app.app_context():
        db.session.add_all(
            [
                SleepRecord(
                    record_date=selected,
                    sleep_start=time(23),
                    sleep_end=time(7),
                    duration_minutes=480,
                    awakenings_count=1,
                    is_primary=True,
                ),
                SleepRecord(
                    record_date=selected,
                    sleep_start=time(14),
                    sleep_end=time(14, 30),
                    duration_minutes=30,
                    awakenings_count=0,
                    is_primary=False,
                    source_record_id="nap-1",
                ),
            ]
        )
        db.session.commit()
        data = get_sleep_page_data(selected)
    assert [item["kind"] for item in data["sleep_sessions"]] == [
        "Sono principal",
        "Cochilo",
    ]


def test_study_subjects_use_only_selected_date(app):
    selected = get_local_today() - timedelta(days=2)
    with app.app_context():
        db.session.add_all(
            [
                StudyRecord(
                    record_date=selected,
                    subject="Matemática",
                    topic="Álgebra",
                    duration_minutes=30,
                    focus_quality="good",
                    record_origin="manual",
                ),
                StudyRecord(
                    record_date=selected - timedelta(days=1),
                    subject="História",
                    topic="Brasil",
                    duration_minutes=60,
                    focus_quality="good",
                    record_origin="manual",
                ),
            ]
        )
        db.session.commit()
        data = build_study_page_data(selected)
    assert [item["name"] for item in data["subjects"]] == ["Matemática"]
