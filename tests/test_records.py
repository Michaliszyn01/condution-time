from datetime import date

from app.models import (
    HydrationRecord,
    MealRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.record_service import (
    get_daily_record_counts,
    get_hydration_total_by_date,
    get_study_records_by_date,
)


TEST_DATE = "2026-07-24"


def study_payload(**changes):
    payload = {
        "record_date": TEST_DATE,
        "subject": "Matemática",
        "topic": "Geometria plana",
        "duration_minutes": 50,
        "questions_count": 10,
        "correct_answers": 8,
        "focus_quality": "Boa",
        "learned_text": "Áreas e propriedades dos triângulos.",
        "difficulty_text": "",
        "record_origin": "Estudo manual",
    }
    payload.update(changes)
    return payload


def sleep_payload(**changes):
    payload = {
        "record_date": TEST_DATE,
        "sleep_start": "22:30",
        "sleep_end": "06:00",
        "perceived_quality": "Boa",
        "awakenings_count": 1,
        "woke_restored": "Sim",
        "notes": "",
        "record_origin": "Manual",
    }
    payload.update(changes)
    return payload


def training_payload(**changes):
    payload = {
        "record_date": TEST_DATE,
        "training_type": "Musculação",
        "activity_name": "Peito e tríceps",
        "duration_minutes": 58,
        "intensity": 8,
        "perceived_performance": "Muito bom",
        "exercises_text": "Supino reto e tríceps pulley",
        "discomfort_level": "Nenhum",
        "discomfort_location": "",
        "notes": "",
    }
    payload.update(changes)
    return payload


def meal_payload(**changes):
    payload = {
        "record_date": TEST_DATE,
        "meal_type": "Almoço",
        "meal_time": "13:00",
        "foods_text": "Frango, arroz, feijão e salada",
        "approximate_amount": "1 prato médio",
        "has_protein": "Sim",
        "has_fruits_or_vegetables": "Sim",
        "perceived_quality": "Boa",
        "notes": "",
    }
    payload.update(changes)
    return payload


def test_create_study_record(client, app):
    response = client.post("/api/records/study", json=study_payload())

    assert response.status_code == 201
    assert response.json["success"] is True
    with app.app_context():
        record = StudyRecord.query.one()
        assert record.duration_minutes == 50
        assert record.focus_quality == "good"
        assert record.record_origin == "manual"


def test_reject_correct_answers_above_questions(client, app):
    response = client.post(
        "/api/records/study",
        json=study_payload(correct_answers=11),
    )

    assert response.status_code == 400
    assert "correct_answers" in response.json["errors"]
    with app.app_context():
        assert StudyRecord.query.count() == 0


def test_sleep_duration_crosses_midnight(client, app):
    response = client.post("/api/records/sleep", json=sleep_payload())

    assert response.status_code == 201
    with app.app_context():
        record = SleepRecord.query.one()
        assert record.duration_minutes == 450
        assert record.record_origin == "manual"


def test_reject_second_sleep_record_for_same_date(client, app):
    first = client.post("/api/records/sleep", json=sleep_payload())
    second = client.post("/api/records/sleep", json=sleep_payload())

    assert first.status_code == 201
    assert second.status_code == 400
    assert (
        second.json["errors"]["record_date"]
        == "Já existe um registro de sono para esta data."
    )
    with app.app_context():
        assert SleepRecord.query.count() == 1


def test_create_valid_training_record(client, app):
    response = client.post("/api/records/training", json=training_payload())

    assert response.status_code == 201
    with app.app_context():
        record = TrainingRecord.query.one()
        assert record.training_type == "strength"
        assert record.perceived_performance == "very_good"
        assert record.discomfort_level == "none"


def test_reject_training_intensity_outside_range(client, app):
    response = client.post(
        "/api/records/training",
        json=training_payload(intensity=11),
    )

    assert response.status_code == 400
    assert "intensity" in response.json["errors"]
    with app.app_context():
        assert TrainingRecord.query.count() == 0


def test_create_meal_record(client, app):
    response = client.post("/api/records/meal", json=meal_payload())

    assert response.status_code == 201
    with app.app_context():
        record = MealRecord.query.one()
        assert record.meal_type == "lunch"
        assert record.has_protein == "yes"
        assert record.has_fruits_or_vegetables == "yes"


def test_convert_liters_to_milliliters(client, app):
    response = client.post(
        "/api/records/hydration",
        json={
            "record_date": TEST_DATE,
            "amount": "0.75",
            "unit": "L",
            "consumed_at": "15:00",
            "notes": "",
        },
    )

    assert response.status_code == 201
    assert response.json["record"]["amount_ml"] == 750
    with app.app_context():
        assert HydrationRecord.query.one().amount_ml == 750


def test_query_records_and_daily_counts(client, app):
    today = date.today().isoformat()
    client.post("/api/records/study", json=study_payload(record_date=today))
    client.post("/api/records/training", json=training_payload(record_date=today))
    client.post("/api/records/meal", json=meal_payload(record_date=today))
    client.post(
        "/api/records/hydration",
        json={
            "record_date": today,
            "amount": 500,
            "unit": "ml",
            "consumed_at": "15:00",
            "notes": "",
        },
    )

    with app.app_context():
        assert len(get_study_records_by_date(date.today())) == 1
        assert get_hydration_total_by_date(date.today()) == 500
        assert get_daily_record_counts(date.today()) == {
            "study": 1,
            "sleep": 0,
            "training": 1,
            "meal": 1,
            "hydration": 1,
            "nutrition": 2,
        }


def test_reject_unknown_fields(client):
    payload = study_payload(unexpected="not allowed")
    response = client.post("/api/records/study", json=payload)

    assert response.status_code == 400
    assert "_schema" in response.json["errors"]
