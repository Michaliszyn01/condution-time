from datetime import datetime, time, timedelta, timezone

import pytest

from app.extensions import db
from app.models import SessionRecord, SleepRecord, StudyRecord
from app.services.analytics_utils import get_local_today
from app.services.history_service import (
    HistoryFilterError,
    get_history_page_data,
    get_unified_history,
    parse_history_filters,
)
from app.services.record_service import (
    create_hydration_record,
    create_meal_record,
    create_sleep_record,
    create_study_record,
    create_training_record,
)


def create_all_categories(target_date):
    create_study_record(
        {
            "record_date": target_date.isoformat(),
            "subject": "Matemática",
            "topic": "Geometria",
            "duration_minutes": 50,
            "questions_count": 10,
            "correct_answers": 8,
            "focus_quality": "Muito boa",
            "learned_text": "Áreas",
            "difficulty_text": "",
            "record_origin": "Estudo manual",
        }
    )
    create_training_record(
        {
            "record_date": target_date.isoformat(),
            "training_type": "Musculação",
            "activity_name": "Peito e tríceps",
            "duration_minutes": 60,
            "intensity": 8,
            "perceived_performance": "Muito bom",
            "exercises_text": "Supino",
            "discomfort_level": "Nenhum",
            "discomfort_location": "",
            "notes": "",
        }
    )
    create_sleep_record(
        {
            "record_date": target_date.isoformat(),
            "sleep_start": "23:00",
            "sleep_end": "07:00",
            "perceived_quality": "Boa",
            "awakenings_count": 1,
            "woke_restored": "Sim",
            "notes": "",
            "record_origin": "Manual",
        }
    )
    create_meal_record(
        {
            "record_date": target_date.isoformat(),
            "meal_type": "Almoço",
            "meal_time": "12:30",
            "foods_text": "Arroz, feijão e frango",
            "approximate_amount": "1 prato",
            "has_protein": "Sim",
            "has_fruits_or_vegetables": "Sim",
            "perceived_quality": "Boa",
            "notes": "",
        }
    )
    create_hydration_record(
        {
            "record_date": target_date.isoformat(),
            "amount": 500,
            "unit": "ml",
            "consumed_at": "14:00",
            "notes": "",
        }
    )
    session = SessionRecord(
        record_date=target_date,
        session_type="study",
        title="Revisar geometria",
        related_category="study",
        target_duration_minutes=50,
        actual_duration_seconds=3600,
        productive_seconds=0,
        distracted_seconds=0,
        status="completed",
        result_text="Concluído",
        learned_text="Reflexão",
        focus_percentage=90,
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        finished_at=datetime.now(timezone.utc),
    )
    db.session.add(session)
    db.session.commit()


def test_history_empty_page(client):
    response = client.get("/historico")

    assert response.status_code == 200
    assert "Nenhum registro encontrado" in response.text
    assert "Histórico" in response.text


def test_unified_history_contains_all_categories_and_is_grouped(app):
    with app.app_context():
        today = get_local_today()
        create_all_categories(today)
        filters = parse_history_filters({"periodo": "today"})
        data = get_history_page_data(filters)

        assert {item["record_type"] for item in data["groups"][0]["items"]} == {
            "study", "training", "sleep", "meal", "hydration", "session"
        }
        assert data["groups"][0]["label"] == "Hoje"
        assert data["summary"]["total_records"] == 6
        assert data["summary"]["duration"] == "2h 50min"
        assert data["summary"]["active_days"] == 1


def test_history_page_renders_populated_groups(client, app):
    with app.app_context():
        create_all_categories(get_local_today())

    response = client.get("/historico?periodo=today")

    assert response.status_code == 200
    assert "Matemática — Geometria" in response.text
    assert "Ver detalhes de Revisar geometria" in response.text


def test_history_renders_imported_sleep_without_subjective_fields(client, app):
    with app.app_context():
        db.session.add(
            SleepRecord(
                record_date=get_local_today(),
                sleep_start=time(23, 0),
                sleep_end=time(7, 0),
                duration_minutes=480,
                perceived_quality=None,
                awakenings_count=0,
                woke_restored=None,
                record_origin="health_connect",
                source_provider="health_connect",
                source_record_id="sleep-regression",
                source_hash="a" * 64,
            )
        )
        db.session.commit()

    response = client.get("/historico")

    assert response.status_code == 200
    assert "Qualidade não informada" in response.text


def test_category_and_case_insensitive_text_filters(app):
    with app.app_context():
        create_all_categories(get_local_today())

        study = get_unified_history(
            parse_history_filters(
                {"categoria": "study", "periodo": "today", "busca": "GEOMETRIA"}
            )
        )
        no_result = get_unified_history(
            parse_history_filters(
                {"categoria": "training", "periodo": "today", "busca": "geometria"}
            )
        )

        assert len(study) == 1
        assert study[0]["title"] == "Matemática — Geometria"
        assert no_result == []


@pytest.mark.parametrize(
    ("period", "start_offset", "end_offset"),
    [
        ("today", 0, 0),
        ("yesterday", 1, 1),
        ("7d", 6, 0),
        ("30d", 29, 0),
    ],
)
def test_quick_period_boundaries(app, period, start_offset, end_offset):
    with app.app_context():
        today = get_local_today()
        filters = parse_history_filters({"periodo": period})

        assert filters.start_date == today - timedelta(days=start_offset)
        assert filters.end_date == today - timedelta(days=end_offset)


def test_month_and_custom_periods(app):
    with app.app_context():
        today = get_local_today()
        month = parse_history_filters({"periodo": "month"})
        custom = parse_history_filters(
            {
                "periodo": "custom",
                "inicio": today.isoformat(),
                "fim": today.isoformat(),
            }
        )

        assert month.start_date == today.replace(day=1)
        assert month.end_date == today
        assert custom.start_date == custom.end_date == today


@pytest.mark.parametrize(
    "args",
    [
        {"periodo": "custom", "inicio": "2026-07-28", "fim": "2026-07-27"},
        {"periodo": "custom", "inicio": "2025-01-01", "fim": "2026-07-27"},
        {"busca": "x" * 101},
        {"categoria": "computer"},
        {"page": 0},
    ],
)
def test_invalid_filters_are_rejected(app, args):
    with app.app_context(), pytest.raises(HistoryFilterError):
        parse_history_filters(args)


def test_history_route_returns_400_for_invalid_period(client):
    response = client.get(
        "/historico?periodo=custom&inicio=2026-07-28&fim=2026-07-27"
    )

    assert response.status_code == 400
    assert "A data inicial não pode ser posterior à final." in response.text


def test_pagination_preserves_global_order(app):
    with app.app_context():
        today = get_local_today()
        for index in range(16):
            db.session.add(
                StudyRecord(
                    record_date=today,
                    subject="Matemática",
                    topic=f"Tópico {index:02d}",
                    duration_minutes=10,
                    focus_quality="good",
                    record_origin="manual",
                    created_at=datetime(2026, 7, 27, 10, index, tzinfo=timezone.utc),
                )
            )
        db.session.commit()

        first = get_history_page_data(
            parse_history_filters({"categoria": "study", "periodo": "today"})
        )
        second = get_history_page_data(
            parse_history_filters(
                {"categoria": "study", "periodo": "today", "page": 2}
            )
        )

        assert first["pagination"]["total_records"] == 16
        assert first["pagination"]["total_pages"] == 2
        assert len(first["groups"][0]["items"]) == 15
        assert len(second["groups"][0]["items"]) == 1
        assert first["groups"][0]["items"][0]["title"].endswith("Tópico 15")


def test_top_category_and_days_active_follow_filtered_results(app):
    with app.app_context():
        today = get_local_today()
        for offset in (0, 1):
            create_study_record(
                {
                    "record_date": (today - timedelta(days=offset)).isoformat(),
                    "subject": "Física",
                    "topic": f"Tema {offset}",
                    "duration_minutes": 30,
                    "questions_count": "",
                    "correct_answers": "",
                    "focus_quality": "Boa",
                    "learned_text": "",
                    "difficulty_text": "",
                    "record_origin": "Estudo manual",
                }
            )
        data = get_history_page_data(parse_history_filters({"periodo": "7d"}))

        assert data["summary"]["top_category"] == "Estudo"
        assert data["summary"]["top_category_count"] == 2
        assert data["summary"]["active_days"] == 2
