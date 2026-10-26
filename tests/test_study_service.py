from datetime import date, datetime, timedelta, timezone

from app.extensions import db
from app.models import StudyRecord
from app.services.study_service import (
    build_study_page_data,
    calculate_provisional_study_score,
    get_monthly_study_heatmap,
    get_study_summary_for_date,
    get_subject_distribution,
    get_weekly_study_data,
)


REFERENCE_DATE = date(2026, 7, 27)


def add_study(
    target_date: date,
    *,
    subject: str = "Matemática",
    topic: str = "Geometria",
    duration: int = 50,
    focus: str = "good",
    questions: int | None = 10,
    correct: int | None = 8,
    learned: str | None = "Aprendizado",
    created_hour: int = 12,
) -> StudyRecord:
    record = StudyRecord(
        record_date=target_date,
        subject=subject,
        topic=topic,
        duration_minutes=duration,
        questions_count=questions,
        correct_answers=correct,
        focus_quality=focus,
        learned_text=learned,
        difficulty_text=None,
        record_origin="manual",
        created_at=datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            created_hour,
            tzinfo=timezone.utc,
        ),
    )
    db.session.add(record)
    db.session.commit()
    return record


def test_empty_daily_summary(app):
    with app.app_context():
        summary = get_study_summary_for_date(REFERENCE_DATE)

    assert summary == {
        "total_minutes": 0,
        "duration": "0 min",
        "sessions": 0,
        "subjects": 0,
        "focus_average": None,
        "score": 0,
    }


def test_daily_summary_sums_duration_sessions_subjects_and_focus(app):
    with app.app_context():
        add_study(REFERENCE_DATE, duration=50, focus="good")
        add_study(
            REFERENCE_DATE,
            subject="matemática",
            duration=40,
            focus="excellent",
        )
        add_study(
            REFERENCE_DATE,
            subject="História",
            duration=30,
            focus="regular",
        )
        summary = get_study_summary_for_date(REFERENCE_DATE)

    assert summary["total_minutes"] == 120
    assert summary["sessions"] == 3
    assert summary["subjects"] == 2
    assert summary["focus_average"] == 67


def test_provisional_score_is_limited_to_twenty(app):
    with app.app_context():
        records = [
            add_study(
                REFERENCE_DATE,
                duration=180,
                focus="excellent",
                questions=31,
                correct=31,
            )
        ]
        assert calculate_provisional_study_score(records) == 20


def test_page_data_compares_with_previous_day(app):
    with app.app_context():
        add_study(REFERENCE_DATE - timedelta(days=1), duration=20, focus="regular")
        add_study(REFERENCE_DATE, duration=120, focus="excellent")
        data = build_study_page_data(REFERENCE_DATE)

    assert data["score"]["raw_value"] == 18
    assert data["score"]["previous_raw_value"] == 9
    assert data["score"]["comparison"] == "+9 pts vs ontem"
    assert data["metrics"][0]["helper"] == "+1h 40min vs ontem"


def test_weekly_chart_covers_last_seven_days(app):
    with app.app_context():
        add_study(REFERENCE_DATE - timedelta(days=6), duration=30)
        add_study(REFERENCE_DATE, duration=120, focus="excellent")
        weekly = get_weekly_study_data(REFERENCE_DATE)

    assert len(weekly) == 7
    assert weekly[0]["date"] == "2026-07-21"
    assert weekly[-1]["date"] == "2026-07-27"
    assert weekly[1]["score"] == 0
    assert weekly[-1]["score"] == 90
    assert weekly[-1]["duration"] == "2h"


def test_subject_distribution_uses_last_period_and_normalizes_case(app):
    with app.app_context():
        add_study(REFERENCE_DATE, subject="Matemática", duration=60)
        add_study(REFERENCE_DATE, subject="matemática", duration=30)
        add_study(REFERENCE_DATE, subject="História", duration=45)
        subjects = get_subject_distribution(
            REFERENCE_DATE - timedelta(days=29),
            REFERENCE_DATE,
        )

    assert subjects[0]["name"] == "Matemática"
    assert subjects[0]["minutes"] == 90
    assert subjects[0]["sessions"] == 2
    assert subjects[0]["score"] == 100
    assert subjects[1]["score"] == 50


def test_monthly_heatmap_levels(app):
    durations = [0, 10, 30, 60, 120, 180]
    with app.app_context():
        for day, duration in enumerate(durations[1:], start=2):
            add_study(date(2026, 7, day), duration=duration)
        heatmap = get_monthly_study_heatmap(2026, 7, REFERENCE_DATE)

    assert [day["level"] for day in heatmap["days"][:6]] == [0, 1, 2, 3, 4, 5]
    assert heatmap["month"] == "Julho de 2026"
    assert heatmap["days"][26]["is_highlighted"] is True


def test_study_page_loads_without_records(client):
    response = client.get("/estudo")

    assert response.status_code == 200
    assert "Nenhum estudo registrado hoje" in response.text
    assert "Maio de 2025" not in response.text
    assert "de julho" in response.text


def test_study_page_loads_real_records(client, app):
    with app.app_context():
        from app.services.study_service import get_local_today

        today = get_local_today()
        add_study(
            today,
            subject="Matemática",
            topic="Geometria plana",
            duration=50,
            focus="very_good",
        )

    response = client.get("/estudo")

    assert response.status_code == 200
    assert "Matemática" in response.text
    assert "Geometria plana" in response.text
    assert "50 min" in response.text
    assert "Foco muito bom" in response.text
