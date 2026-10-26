from app.extensions import db
from app.models import SessionRecord
from app.services.analytics_utils import get_local_today


def valid_payload(**overrides):
    payload = {
        "session_type": "programming",
        "title": "Implementar API",
        "related_category": "computer",
        "target_duration_minutes": 25,
        "computer_monitoring_enabled": False,
        "objective_text": "Concluir o endpoint",
    }
    payload.update(overrides)
    return payload


def test_full_session_api_flow(client, app):
    created = client.post("/api/sessions", json=valid_payload())
    assert created.status_code == 201
    body = created.get_json()
    session_id = body["session"]["id"]
    assert body["session"]["status"] == "running"

    active = client.get("/api/sessions/active").get_json()
    assert active["active_session"]["id"] == session_id

    paused = client.post(
        f"/api/sessions/{session_id}/pause",
        json={"actual_duration_seconds": 30},
    )
    assert paused.status_code == 200
    assert paused.get_json()["session"]["status"] == "paused"

    resumed = client.post(f"/api/sessions/{session_id}/resume", json={})
    assert resumed.status_code == 200

    finished = client.post(
        f"/api/sessions/{session_id}/finish",
        json={
            "actual_duration_seconds": 40,
            "productive_seconds": 0,
            "distracted_seconds": 0,
        },
    )
    assert finished.status_code == 200
    assert finished.get_json()["session_bonus"]["score"] == 2

    summary = client.patch(
        f"/api/sessions/{session_id}/summary",
        json={
            "result_text": "Endpoint concluído",
            "learned_text": "Aprendi o fluxo",
            "difficulty_text": "",
            "self_rating": 8,
        },
    )
    assert summary.status_code == 200
    assert summary.get_json()["session_bonus"]["score"] == 4
    assert summary.get_json()["daily_session_bonus"]["score"] == 4


def test_api_rejects_invalid_payload_transition_and_duplicate_finish(client):
    invalid = client.post(
        "/api/sessions",
        json=valid_payload(related_category="study"),
    )
    assert invalid.status_code == 400
    assert "related_category" in invalid.get_json()["errors"]

    created = client.post("/api/sessions", json=valid_payload()).get_json()
    session_id = created["session"]["id"]
    bad_pause = client.post(
        f"/api/sessions/{session_id}/pause",
        json={"actual_duration_seconds": -1},
    )
    assert bad_pause.status_code == 400

    finished = client.post(
        f"/api/sessions/{session_id}/finish",
        json={
            "actual_duration_seconds": 1,
            "productive_seconds": 0,
            "distracted_seconds": 0,
        },
    )
    assert finished.status_code == 200
    duplicate = client.post(
        f"/api/sessions/{session_id}/finish",
        json={
            "actual_duration_seconds": 1,
            "productive_seconds": 0,
            "distracted_seconds": 0,
        },
    )
    assert duplicate.status_code == 409


def test_api_cancel_has_zero_bonus(client):
    created = client.post("/api/sessions", json=valid_payload()).get_json()
    session_id = created["session"]["id"]
    response = client.post(
        f"/api/sessions/{session_id}/cancel",
        json={"actual_duration_seconds": 0},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["session"]["status"] == "cancelled"
    assert body["session_bonus"]["score"] == 0
    assert body["daily_session_bonus"]["score"] == 0


def test_session_page_embeds_active_recovery_data(client, app):
    with app.app_context():
        record = SessionRecord(
            record_date=get_local_today(),
            session_type="other",
            title="Sessão recuperável",
            related_category="other",
            target_duration_minutes=25,
            actual_duration_seconds=20,
            productive_seconds=0,
            distracted_seconds=0,
            computer_monitoring_enabled=False,
            status="paused",
        )
        db.session.add(record)
        db.session.commit()

    response = client.get("/sessao")

    assert response.status_code == 200
    assert "Sess\\u00e3o recuper\\u00e1vel" in response.text
    assert "data-session-recovery" in response.text
    assert "Nenhum dado disponível sem monitoramento do sistema." in response.text


def test_session_page_without_active_session_embeds_null(client):
    response = client.get("/sessao")

    assert response.status_code == 200
    assert "data-active-session" in response.text
    assert "null" in response.text
