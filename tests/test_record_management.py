from app.extensions import db
from app.models import SessionRecord
from app.services.analytics_utils import get_local_today
from app.services.home_service import get_home_page_data


def post_record(client, record_type, payload):
    response = client.post(f"/api/records/{record_type}", json=payload)
    assert response.status_code == 201
    return response.get_json()["record"]["id"]


def study_payload(**overrides):
    payload = {
        "record_date": get_local_today().isoformat(),
        "subject": "Matemática",
        "topic": "Geometria",
        "duration_minutes": 50,
        "questions_count": 10,
        "correct_answers": 8,
        "focus_quality": "Boa",
        "learned_text": "Áreas",
        "difficulty_text": "",
        "record_origin": "Estudo manual",
    }
    payload.update(overrides)
    return payload


def training_payload(**overrides):
    payload = {
        "record_date": get_local_today().isoformat(),
        "training_type": "Musculação",
        "activity_name": "Peito",
        "duration_minutes": 45,
        "intensity": 7,
        "perceived_performance": "Bom",
        "exercises_text": "Supino",
        "discomfort_level": "Nenhum",
        "discomfort_location": "",
        "notes": "",
    }
    payload.update(overrides)
    return payload


def sleep_payload(**overrides):
    payload = {
        "record_date": get_local_today().isoformat(),
        "sleep_start": "23:00",
        "sleep_end": "07:00",
        "perceived_quality": "Boa",
        "awakenings_count": 1,
        "woke_restored": "Sim",
        "notes": "",
        "record_origin": "Manual",
    }
    payload.update(overrides)
    return payload


def meal_payload(**overrides):
    payload = {
        "record_date": get_local_today().isoformat(),
        "meal_type": "Almoço",
        "meal_time": "12:00",
        "foods_text": "Arroz e feijão",
        "approximate_amount": "1 prato",
        "has_protein": "Sim",
        "has_fruits_or_vegetables": "Sim",
        "perceived_quality": "Boa",
        "notes": "",
    }
    payload.update(overrides)
    return payload


def hydration_payload(**overrides):
    payload = {
        "record_date": get_local_today().isoformat(),
        "amount": 500,
        "unit": "ml",
        "consumed_at": "14:00",
        "notes": "",
    }
    payload.update(overrides)
    return payload


def test_study_detail_and_valid_edit(client):
    record_id = post_record(client, "study", study_payload())

    detail = client.get(f"/api/records/study/{record_id}")
    edited = client.patch(
        f"/api/records/study/{record_id}",
        json=study_payload(topic="Trigonometria", correct_answers=9),
    )

    assert detail.status_code == 200
    assert detail.get_json()["record"]["editable"] is True
    assert edited.status_code == 200
    assert edited.get_json()["record"]["data"]["topic"] == "Trigonometria"


def test_study_edit_validation(client):
    record_id = post_record(client, "study", study_payload())

    too_many = client.patch(
        f"/api/records/study/{record_id}",
        json=study_payload(questions_count=5, correct_answers=6),
    )
    invalid_duration = client.patch(
        f"/api/records/study/{record_id}",
        json=study_payload(duration_minutes=0),
    )

    assert too_many.status_code == 400
    assert "correct_answers" in too_many.get_json()["errors"]
    assert invalid_duration.status_code == 400


def test_training_edit_and_validation(client):
    record_id = post_record(client, "training", training_payload())

    edited = client.patch(
        f"/api/records/training/{record_id}",
        json=training_payload(activity_name="Corrida", intensity=9),
    )
    bad_intensity = client.patch(
        f"/api/records/training/{record_id}",
        json=training_payload(intensity=11),
    )
    missing_location = client.patch(
        f"/api/records/training/{record_id}",
        json=training_payload(discomfort_level="Moderado", discomfort_location=""),
    )

    assert edited.status_code == 200
    assert edited.get_json()["record"]["data"]["intensity"] == 9
    assert bad_intensity.status_code == 400
    assert missing_location.status_code == 400
    assert "discomfort_location" in missing_location.get_json()["errors"]


def test_sleep_edit_recalculates_midnight_duration_and_detects_conflict(client):
    first_id = post_record(client, "sleep", sleep_payload())
    edited = client.patch(
        f"/api/records/sleep/{first_id}",
        json=sleep_payload(sleep_start="23:30", sleep_end="07:15"),
    )

    assert edited.status_code == 200
    duration_detail = next(
        field["value"]
        for field in edited.get_json()["record"]["details"]
        if field["label"] == "Duração calculada"
    )
    assert duration_detail == "465 min"

    other_date = (get_local_today().replace(day=max(1, get_local_today().day - 1)))
    second_id = post_record(
        client,
        "sleep",
        sleep_payload(record_date=other_date.isoformat()),
    )
    conflict = client.patch(
        f"/api/records/sleep/{second_id}",
        json=sleep_payload(record_date=get_local_today().isoformat()),
    )
    assert conflict.status_code == 409


def test_meal_and_hydration_edits(client):
    meal_id = post_record(client, "meal", meal_payload())
    water_id = post_record(client, "hydration", hydration_payload())

    meal = client.patch(
        f"/api/records/meal/{meal_id}",
        json=meal_payload(foods_text="Sopa", perceived_quality="Excelente"),
    )
    litres = client.patch(
        f"/api/records/hydration/{water_id}",
        json=hydration_payload(amount="1.5", unit="L"),
    )

    assert meal.status_code == 200
    assert meal.get_json()["record"]["data"]["foods_text"] == "Sopa"
    assert litres.status_code == 200
    assert litres.get_json()["record"]["data"]["amount"] == 1500


def test_meal_enum_and_hydration_amount_validation(client):
    meal_id = post_record(client, "meal", meal_payload())
    water_id = post_record(client, "hydration", hydration_payload())

    bad_meal = client.patch(
        f"/api/records/meal/{meal_id}",
        json=meal_payload(meal_type="Brunch"),
    )
    bad_water = client.patch(
        f"/api/records/hydration/{water_id}",
        json=hydration_payload(amount=0),
    )

    assert bad_meal.status_code == 400
    assert bad_water.status_code == 400


def test_session_is_readonly(client, app):
    with app.app_context():
        session = SessionRecord(
            record_date=get_local_today(),
            session_type="study",
            title="Somente leitura",
            related_category="study",
            status="completed",
            actual_duration_seconds=60,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id

    detail = client.get(f"/api/records/session/{session_id}")
    edit = client.patch(f"/api/records/session/{session_id}", json={})
    delete = client.delete(f"/api/records/session/{session_id}")

    assert detail.status_code == 200
    assert detail.get_json()["record"]["editable"] is False
    assert detail.get_json()["record"]["deletable"] is False
    assert edit.status_code == 403
    assert delete.status_code == 403


def test_delete_every_editable_type_and_missing_record(client):
    ids = {
        "study": post_record(client, "study", study_payload()),
        "training": post_record(client, "training", training_payload()),
        "sleep": post_record(client, "sleep", sleep_payload()),
        "meal": post_record(client, "meal", meal_payload()),
        "hydration": post_record(client, "hydration", hydration_payload()),
    }

    for record_type, record_id in ids.items():
        response = client.delete(f"/api/records/{record_type}/{record_id}")
        assert response.status_code == 200
        assert client.get(
            f"/api/records/{record_type}/{record_id}"
        ).status_code == 404

    assert client.delete("/api/records/study/99999").status_code == 404
    assert client.delete("/api/records/invalid/1").status_code == 400


def test_deleting_last_study_changes_home_and_score(client, app):
    record_id = post_record(client, "study", study_payload())
    with app.app_context():
        before = get_home_page_data(get_local_today())
    deleted = client.delete(f"/api/records/study/{record_id}")
    with app.app_context():
        after = get_home_page_data(get_local_today())

    assert deleted.status_code == 200
    assert before["categories"][0]["evaluated"] is True
    assert after["categories"][0]["evaluated"] is False
    assert after["score"]["value"] < before["score"]["value"]
