from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from app.extensions import db
from app.models import (
    BodyMeasurement,
    ComputerActivityBlock,
    DailyHealthSummary,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
    UserProfile,
)
from app.services.experience_service import format_achievement_value, level_progress
from app.services.profile_page_service import (
    get_health_profile_data,
    get_sleep_profile_data,
    get_study_profile_data,
)


def test_achievement_formatter_uses_declared_units():
    assert format_achievement_value(74, "seconds") == "1 min 14 s"
    assert format_achievement_value(3_600, "seconds") == "1h"
    assert format_achievement_value(36_000, "seconds") == "10h"
    assert format_achievement_value(74, "minutes") == "1h14"
    assert format_achievement_value(50_000, "meters") == "50 km"
    assert format_achievement_value(1, "sessions") == "1 sessão"
    assert format_achievement_value(3, "sessions") == "3 sessões"


def test_level_curve_is_consistent_with_total_and_current_xp():
    progress = level_progress(548)
    assert progress == {
        "level": 4,
        "total_xp": 548,
        "current_xp": 98,
        "next_level_xp": 250,
        "progress_percent": 39,
    }


def test_profile_tabs_and_period_are_persisted_in_url(client):
    for tab, heading in (
        ("overview", "Visão geral"),
        ("study", "Estudos"),
        ("health", "Corpo e saúde"),
        ("training", "Treinos"),
        ("sleep", "Sono"),
        ("computer", "Computador"),
        ("achievements", "Conquistas"),
        ("goals", "Metas"),
    ):
        response = client.get(f"/perfil?tab={tab}&period=90d")
        assert response.status_code == 200
        assert heading in response.text
        assert f'tab={tab}&amp;period=90d' in response.text
        assert 'aria-selected="true"' in response.text
        assert ">90 dias<" in response.text


def test_profile_header_uses_database_name_initials_and_streak(client, app):
    today = date.today()
    with app.app_context():
        db.session.add(UserProfile(name="Marcos Eduardo", avatar_initials="ME"))
        for offset in (0, 1, 2):
            db.session.add(
                StudyRecord(
                    record_date=today - timedelta(days=offset),
                    subject="História",
                    topic="Revisão",
                    duration_minutes=20,
                    focus_quality="Boa",
                    record_origin="manual",
                )
            )
        db.session.commit()
    response = client.get("/perfil?tab=overview&period=7d")
    assert response.status_code == 200
    assert "Marcos Eduardo" in response.text
    assert ">ME<" in response.text
    assert "Sequência atual: 3 dias" in response.text
    assert "XP total" in response.text


def test_study_profile_has_real_subject_level_color_questions_and_chart(app):
    with app.app_context():
        db.session.add(
            StudyRecord(
                record_date=date.today(),
                subject="Matemática",
                topic="Álgebra",
                duration_minutes=150,
                questions_count=10,
                correct_answers=8,
                focus_quality="Excelente",
                record_origin="manual",
            )
        )
        db.session.commit()
        data = get_study_profile_data("30d")
        subject = data["subjects"][0]
        assert data["has_data"]
        assert subject["display_name"] == "Matemática"
        assert subject["xp"] == 168
        assert subject["level"] == 2
        assert subject["current_xp"] == 68
        assert subject["next_level_xp"] == 150
        assert subject["questions"] == 10
        assert subject["accuracy"] == 80
        assert subject["color"] == "#246BFD"
        assert data["chart"]["datasets"][0]["data"]


def test_health_profile_omits_missing_cards_and_builds_weight_rolling(app):
    now = datetime.now(timezone.utc)
    with app.app_context():
        for index, weight in enumerate((80.0, 79.5, 79.0)):
            db.session.add(
                BodyMeasurement(
                    measured_at=now - timedelta(days=2 - index),
                    weight_kg=weight,
                    source_provider="health_connect",
                    source_record_id=f"weight-{index}",
                    source_hash=f"hash-{index}",
                )
            )
        db.session.add(
            DailyHealthSummary(
                record_date=date.today(),
                steps=8_000,
                vo2_max=42.0,
                source_hash="daily-hash",
            )
        )
        db.session.commit()
        data = get_health_profile_data("30d")
        assert data["weight"]["first"] == 80.0
        assert data["weight"]["latest"] == 79.0
        assert data["weight"]["difference"] == -1.0
        assert data["weight"]["points"][-1]["rolling"] == 79.5
        labels = {item["label"] for item in data["metrics"]}
        assert "Peso atual" in labels
        assert "Passos médios" in labels
        assert "Gordura corporal" not in labels


def test_sleep_profile_uses_watch_stages_and_efficiency(app):
    start = datetime.now(timezone.utc).replace(hour=22, minute=0, second=0, microsecond=0)
    stages = [
        {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "type": 4},
        {"start": (start + timedelta(hours=1)).isoformat(), "end": (start + timedelta(hours=2)).isoformat(), "type": 5},
        {"start": (start + timedelta(hours=2)).isoformat(), "end": (start + timedelta(hours=3)).isoformat(), "type": 6},
        {"start": (start + timedelta(hours=3)).isoformat(), "end": (start + timedelta(hours=4)).isoformat(), "type": 1},
    ]
    with app.app_context():
        db.session.add(
            SleepRecord(
                record_date=date.today(),
                sleep_start=time(22, 0),
                sleep_end=time(2, 0),
                duration_minutes=240,
                awakenings_count=1,
                record_origin="health_connect",
                sleep_stages_json=json.dumps(stages),
            )
        )
        db.session.commit()
        data = get_sleep_profile_data("30d")
        assert data["has_data"]
        assert {item["key"] for item in data["stages"]} == {
            "light",
            "deep",
            "rem",
            "awake",
        }
        efficiency = next(
            item["value"] for item in data["metrics"] if item["label"] == "Eficiência média"
        )
        assert efficiency == "75%"


def test_computer_and_training_endpoints_use_real_classified_data(client, app):
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add(
            TrainingRecord(
                record_date=date.today(),
                training_type="running",
                activity_name="Corrida",
                duration_minutes=40,
                distance_meters=5_000,
                source_exercise_type=56,
            )
        )
        db.session.add_all(
            [
                ComputerActivityBlock(
                    record_date=date.today(),
                    executable_name="code.exe",
                    friendly_name="Visual Studio Code",
                    classification="productive",
                    category="programming",
                    classification_source="default_rule",
                    started_at=now,
                    ended_at=now + timedelta(minutes=30),
                    duration_seconds=1_800,
                    was_idle=False,
                    project_key="condution_time",
                    project_display_name="Condution Time",
                ),
                ComputerActivityBlock(
                    record_date=date.today(),
                    executable_name="chrome.exe",
                    friendly_name="Google Chrome",
                    classification="distracting",
                    category="entertainment",
                    classification_source="default_rule",
                    started_at=now + timedelta(minutes=30),
                    ended_at=now + timedelta(minutes=40),
                    duration_seconds=600,
                    was_idle=False,
                ),
            ]
        )
        db.session.commit()
    training = client.get("/api/profile/training?period=30d").get_json()
    computer = client.get("/api/profile/computer?period=30d").get_json()
    assert training["has_data"]
    assert training["modalities"][0]["name"] != "running"
    assert training["modalities"][0]["distance"] == 5_000
    assert computer["has_data"]
    assert computer["top_project"] == "Condution Time"
    assert computer["top_productive_app"] == "Visual Studio Code"
    assert computer["top_distracting_app"] == "Google Chrome"
    assert computer["vscode_seconds"] == 1_800


def test_achievement_filters_units_and_progress_limit(client, app):
    with app.app_context():
        db.session.add(
            ComputerActivityBlock(
                record_date=date.today(),
                executable_name="code.exe",
                friendly_name="Visual Studio Code",
                classification="productive",
                category="programming",
                classification_source="default_rule",
                started_at=datetime.now(timezone.utc),
                ended_at=datetime.now(timezone.utc) + timedelta(hours=2),
                duration_seconds=7_200,
                was_idle=False,
            )
        )
        db.session.commit()
    payload = client.get(
        "/api/profile/achievements?category=Computador&status=all"
    ).get_json()
    assert payload["items"]
    first_hour = next(
        item for item in payload["items"]
        if item["achievement_key"] == "computer_first_hour"
    )
    assert first_hour["unit"] == "seconds"
    assert first_hour["current_label"] == "2h"
    assert first_hour["target_label"] == "1h"
    assert first_hour["progress_percent"] == 100
    assert first_hour["unlocked"]


def test_goals_patch_is_separate_validated_and_persistent(client, app):
    response = client.patch(
        "/api/profile/goals",
        json={
            "weekly_study_minutes": 300,
            "weekly_training_count": 4,
            "sleep_target_minutes": 480,
            "hydration_target_ml": 2_500,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["goals"]["goal_values"]["weekly_study_minutes"] == 300
    with app.app_context():
        profile = db.session.scalar(db.select(UserProfile))
        assert profile.weekly_study_minutes == 300
        assert profile.hydration_target_ml == 2_500
    assert client.patch(
        "/api/profile/goals", json={"academic_goal": "campo indevido"}
    ).status_code == 400
    assert client.patch(
        "/api/profile/goals", json={"weekly_study_minutes": 0}
    ).status_code == 400
