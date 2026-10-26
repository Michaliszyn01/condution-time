from datetime import date, datetime, timedelta, timezone

from app.extensions import db
from app.models import TrainingRecord
from app.services.training_service import (
    calculate_provisional_training_score,
    get_monthly_training_heatmap,
    get_training_area_distribution,
    get_training_page_data,
    get_training_summary_for_date,
    get_weekly_training_data,
)


REFERENCE_DATE = date(2026, 7, 27)


def add_training(
    target_date: date,
    *,
    training_type: str = "strength",
    activity_name: str = "Peito e tríceps",
    duration: int = 58,
    intensity: int = 8,
    performance: str = "very_good",
    exercises: str | None = "Supino e tríceps pulley",
    discomfort: str = "none",
    discomfort_location: str | None = None,
    created_hour: int = 12,
) -> TrainingRecord:
    record = TrainingRecord(
        record_date=target_date,
        training_type=training_type,
        activity_name=activity_name,
        duration_minutes=duration,
        intensity=intensity,
        perceived_performance=performance,
        exercises_text=exercises,
        discomfort_level=discomfort,
        discomfort_location=discomfort_location,
        notes=None,
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


def test_training_page_and_summary_without_records(client, app):
    with app.app_context():
        summary = get_training_summary_for_date(REFERENCE_DATE)

    response = client.get("/treino")

    assert summary == {
        "sessions": 0,
        "total_minutes": 0,
        "duration": "0 min",
        "intensity_average": None,
        "score": 0,
    }
    assert response.status_code == 200
    assert "Nenhum treino registrado hoje" in response.text
    assert "Nenhum treino registrado nos últimos 30 dias." in response.text
    assert "Maio de 2025" not in response.text


def test_training_summary_sums_duration_sessions_and_intensity(app):
    with app.app_context():
        add_training(REFERENCE_DATE, duration=40, intensity=7)
        add_training(
            REFERENCE_DATE,
            duration=35,
            intensity=8,
            created_hour=13,
        )
        summary = get_training_summary_for_date(REFERENCE_DATE)

    assert summary["sessions"] == 2
    assert summary["total_minutes"] == 75
    assert summary["duration"] == "1h 15min"
    assert summary["intensity_average"] == 7.5


def test_provisional_training_score_is_limited_to_twenty(app):
    with app.app_context():
        records = [
            add_training(
                REFERENCE_DATE - timedelta(days=offset),
                duration=90 if offset == 0 else 20,
                intensity=8,
                performance="excellent",
            )
            for offset in range(4)
        ]
        score = calculate_provisional_training_score(records[:1], records)

    assert score == 20


def test_training_page_compares_with_yesterday_and_calculates_consistency(app):
    with app.app_context():
        add_training(
            REFERENCE_DATE - timedelta(days=1),
            duration=20,
            intensity=4,
            performance="regular",
            exercises=None,
        )
        add_training(
            REFERENCE_DATE - timedelta(days=2),
            duration=30,
        )
        add_training(
            REFERENCE_DATE - timedelta(days=4),
            duration=25,
        )
        add_training(
            REFERENCE_DATE,
            duration=60,
            intensity=10,
            performance="excellent",
        )
        data = get_training_page_data(REFERENCE_DATE)

    assert data["score"]["raw_value"] == 19
    assert data["score"]["previous_raw_value"] == 11
    assert data["score"]["comparison"] == "+8 pts vs ontem"
    assert data["metrics"][3]["value"] == "4 dias"
    assert data["metrics"][3]["helper"] == "Boa"


def test_weekly_training_data_contains_scores_duration_and_sessions(app):
    with app.app_context():
        add_training(
            REFERENCE_DATE - timedelta(days=6),
            duration=20,
            exercises=None,
        )
        add_training(REFERENCE_DATE, duration=60, intensity=10)
        add_training(
            REFERENCE_DATE,
            duration=30,
            intensity=8,
            created_hour=13,
        )
        weekly = get_weekly_training_data(REFERENCE_DATE)

    assert len(weekly) == 7
    assert weekly[0]["date"] == "2026-07-21"
    assert weekly[1]["score"] == 0
    assert weekly[-1]["duration"] == "1h 30min"
    assert weekly[-1]["sessions"] == 2
    assert weekly[-1]["tooltip_lines"] == ["1h 30min", "2 treinos"]


def test_training_area_distribution_groups_types(app):
    with app.app_context():
        add_training(REFERENCE_DATE, training_type="strength", duration=120)
        add_training(
            REFERENCE_DATE,
            training_type="running",
            activity_name="Corrida",
            duration=40,
            created_hour=13,
        )
        add_training(
            REFERENCE_DATE,
            training_type="cycling",
            activity_name="Ciclismo",
            duration=20,
            created_hour=14,
        )
        add_training(
            REFERENCE_DATE,
            training_type="mobility",
            activity_name="Alongamento",
            duration=30,
            created_hour=15,
        )
        distribution = get_training_area_distribution(
            REFERENCE_DATE - timedelta(days=29),
            REFERENCE_DATE,
        )

    assert [item["name"] for item in distribution] == [
        "Treino de força",
        "Corrida",
        "Mobilidade",
        "Ciclismo",
    ]
    assert distribution[0]["score"] == 100
    assert distribution[1]["minutes"] == 40
    assert distribution[1]["sessions"] == 1
    assert distribution[1]["score"] == 33


def test_monthly_training_heatmap_levels_and_details(app):
    durations = [10, 20, 40, 60, 90]
    with app.app_context():
        for day, duration in enumerate(durations, start=2):
            add_training(
                date(2026, 7, day),
                training_type="running",
                activity_name=f"Corrida {day}",
                duration=duration,
            )
        heatmap = get_monthly_training_heatmap(2026, 7, REFERENCE_DATE)

    assert [day["level"] for day in heatmap["days"][:6]] == [0, 1, 2, 3, 4, 5]
    assert heatmap["month"] == "Julho de 2026"
    assert "Corrida" in heatmap["days"][1]["title"]
    assert heatmap["days"][26]["is_highlighted"] is True


def test_recent_training_records_are_ordered_and_translate_discomfort(app):
    with app.app_context():
        add_training(
            REFERENCE_DATE,
            activity_name="Corrida leve",
            training_type="running",
            discomfort="none",
            created_hour=11,
        )
        add_training(
            REFERENCE_DATE,
            activity_name="Treino de ombro",
            discomfort="mild",
            discomfort_location="ombro direito",
            created_hour=14,
        )
        data = get_training_page_data(REFERENCE_DATE)

    assert data["sessions"][0]["name"] == "Treino de ombro"
    assert "Desconforto leve em ombro direito" in data["sessions"][0]["meta"]
    assert data["sessions"][1]["name"] == "Corrida leve"
    assert "Desconforto" not in data["sessions"][1]["meta"]
    assert "Corrida" in data["sessions"][1]["meta"]


def test_training_page_loads_real_data(client, app):
    with app.app_context():
        from app.services.analytics_utils import get_local_today

        today = get_local_today()
        add_training(
            today,
            activity_name="Peito e tríceps",
            duration=58,
            intensity=8,
            discomfort="moderate",
            discomfort_location="ombro",
        )

    response = client.get("/treino")

    assert response.status_code == 200
    assert "Peito e tríceps" in response.text
    assert "58 min" in response.text
    assert "Intensidade 8/10" in response.text
    assert "Desempenho muito bom" in response.text
    assert "Desconforto moderado em ombro" in response.text
