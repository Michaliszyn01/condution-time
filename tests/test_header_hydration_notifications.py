import pytest

from app.extensions import db
from app.models import AppNotification, HydrationRecord, StudyRecord, UserProfile
from app.services.analytics_utils import get_local_today
from app.services.experience_service import sync_experience_ledger
from app.services.notification_service import (
    create_cooldown_notification,
    create_notification,
)


HEADER_ROUTES = (
    "/",
    "/perfil",
    "/estudo",
    "/treino",
    "/sono",
    "/alimentacao",
    "/computador",
    "/registrar",
    "/sessao",
    "/historico",
    "/configuracoes",
    "/notificacoes",
)


@pytest.mark.parametrize("route", HEADER_ROUTES)
def test_global_header_is_present_on_every_requested_page(client, route):
    response = client.get(route)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data-global-header" in html
    assert 'class="water-bottle-icon"' in html
    assert 'data-lucide="bell"' in html
    assert "quadrado branco vazio" not in html


def test_header_uses_real_profile_name_initials_and_browser_explanation(client):
    assert "Usuário" in client.get("/").get_data(as_text=True)
    response = client.patch(
        "/api/profile",
        json={"name": "Marcos Eduardo", "avatar_initials": ""},
    )
    assert response.status_code == 200
    html = client.get("/").get_data(as_text=True)
    assert "Marcos Eduardo" in html
    assert ">ME<" in html
    assert "Disponível apenas no aplicativo Windows" in html


@pytest.mark.parametrize("amount", (200, 300, 500, 1234))
def test_canonical_quick_hydration_records_real_integer_amount(
    client,
    app,
    amount,
):
    response = client.post(
        "/api/hydration/quick",
        json={"amount_ml": amount},
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"] == f"{amount} ml registrados"
    assert payload["total_ml"] == amount
    assert payload["recent_records"][0]["amount_ml"] == amount
    with app.app_context():
        record = db.session.scalar(db.select(HydrationRecord))
        assert record.record_date == get_local_today()
        assert record.amount_ml == amount
        assert record.consumed_at is not None


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"amount_ml": 0},
        {"amount_ml": 9},
        {"amount_ml": 5001},
        {"amount_ml": -100},
        {"amount_ml": "300"},
        {"amount_ml": 300.5},
        {"amount_ml": 300, "record_date": "2020-01-01"},
    ),
)
def test_quick_hydration_rejects_invalid_or_extra_fields(client, payload):
    response = client.post("/api/hydration/quick", json=payload)
    assert response.status_code == 400


def test_hydration_summary_uses_profile_goal_and_recent_history(client, app):
    with app.app_context():
        db.session.add(UserProfile(name="Marcos Eduardo", hydration_target_ml=2500))
        db.session.commit()
    client.post("/api/hydration/quick", json={"amount_ml": 500})
    payload = client.get("/api/hydration/today").get_json()
    assert payload["goal_ml"] == 2500
    assert payload["total_ml"] == 500
    assert payload["percentage"] == 20
    assert payload["current_time"]
    assert len(payload["recent_records"]) == 1


def test_notifications_deduplicate_count_read_all_delete_and_paginate(client, app):
    with app.app_context():
        first, created = create_notification(
            notification_key="test:one",
            type="backup_created",
            title="Backup criado",
            message="Seus dados foram protegidos.",
            severity="success",
        )
        duplicate, created_again = create_notification(
            notification_key="test:one",
            type="backup_created",
            title="Backup criado",
            message="Seus dados foram protegidos.",
            severity="success",
        )
        assert created is True
        assert created_again is False
        assert duplicate.id == first.id
        for index in range(21):
            create_notification(
                notification_key=f"test:page:{index}",
                type="application_error",
                title="Aviso",
                message="Evento real de teste.",
            )
        first_id = first.id

    count = client.get("/api/notifications/unread-count").get_json()
    assert count["unread_count"] == 22
    page = client.get("/api/notifications?per_page=5&page=2").get_json()
    assert page["total"] == 22
    assert page["pages"] == 5
    assert len(page["items"]) == 5

    read = client.post(f"/api/notifications/{first_id}/read").get_json()
    assert read["notification"]["is_read"] is True
    assert read["unread_count"] == 21
    assert client.post("/api/notifications/read-all").get_json()["updated"] == 21
    assert client.delete(f"/api/notifications/{first_id}").status_code == 200
    assert client.delete(f"/api/notifications/{first_id}").status_code == 404


def test_achievement_unlock_creates_one_real_notification(app):
    with app.app_context():
        db.session.add(
            StudyRecord(
                record_date=get_local_today(),
                subject="Matemática",
                topic="Funções",
                duration_minutes=30,
                focus_quality="good",
                record_origin="manual",
            )
        )
        db.session.commit()
        sync_experience_ledger()
        sync_experience_ledger()
        items = list(
            db.session.scalars(
                db.select(AppNotification).where(
                    AppNotification.type == "achievement_unlocked"
                )
            )
        )
        assert len(items) == 1
        assert items[0].notification_key == "achievement:study_first"


def test_application_error_notification_uses_cooldown_bucket(app):
    with app.app_context():
        for _ in range(3):
            create_cooldown_notification(
                notification_key="application-error",
                type="application_error",
                title="Erro",
                message="Falha local.",
                severity="error",
                cooldown_minutes=60,
            )
        assert (
            db.session.scalar(
                db.select(db.func.count(AppNotification.id)).where(
                    AppNotification.type == "application_error"
                )
            )
            == 1
        )


def test_manual_monitor_pause_is_notified_once_and_resume_resolves(client, app):
    class Agent:
        paused = False

        def pause(self):
            changed = not self.paused
            self.paused = True
            return changed

        def resume(self):
            changed = self.paused
            self.paused = False
            return changed

        def status(self):
            return {
                "status": "paused" if self.paused else "running",
                "paused": self.paused,
                "available": True,
            }

    app.config["COMPUTER_MONITOR_AGENT"] = Agent()
    assert client.post("/api/computer-monitor/pause").status_code == 200
    assert client.post("/api/computer-monitor/pause").status_code == 200
    with app.app_context():
        item = db.session.scalar(
            db.select(AppNotification).where(
                AppNotification.notification_key == "monitoring:paused"
            )
        )
        assert item is not None
        assert item.is_read is False
    assert client.post("/api/computer-monitor/resume").status_code == 200
    with app.app_context():
        assert db.session.scalar(
            db.select(AppNotification.is_read).where(
                AppNotification.notification_key == "monitoring:paused"
            )
        ) is True


def test_monitor_error_notification_has_cooldown(client, app):
    class FailingAgent:
        def pause(self):
            raise RuntimeError("falha local")

    app.config["COMPUTER_MONITOR_AGENT"] = FailingAgent()
    for _ in range(2):
        with pytest.raises(RuntimeError, match="falha local"):
            client.post("/api/computer-monitor/pause")
    with app.app_context():
        assert (
            db.session.scalar(
                db.select(db.func.count(AppNotification.id)).where(
                    AppNotification.type == "monitoring_error"
                )
            )
            == 1
        )
