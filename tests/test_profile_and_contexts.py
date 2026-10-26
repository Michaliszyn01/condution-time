from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.extensions import db
from app.models import (
    ComputerActivityBlock,
    ProjectRule,
    StudyRecord,
    StudySubjectProgress,
)
from app.services.profile_service import level_from_xp, rebuild_study_subject_progress
from desktop.monitoring.aggregator import ActivityAggregator
from desktop.monitoring.classifier import ApplicationClassifier
from desktop.monitoring.state import ForegroundApplication


class ContextRepository:
    def __init__(self, *, manual=None, projects=None):
        self.manual = manual
        self.projects = projects or []

    def get_application_rule(self, _executable):
        return self.manual

    def get_project_rules(self):
        return self.projects


def test_default_chatgpt_and_code_are_productive():
    classifier = ApplicationClassifier(ContextRepository())
    chatgpt = classifier.classify("chatgpt.exe")
    code = classifier.classify("code.exe")
    assert (chatgpt.classification, chatgpt.category) == ("productive", "study")
    assert (code.classification, code.category) == ("productive", "programming")


def test_chrome_chatgpt_is_allowlisted_but_regular_chrome_is_neutral():
    classifier = ApplicationClassifier(ContextRepository())
    recognized = classifier.classify(
        "chrome.exe",
        transient_title="Minha conversa - ChatGPT",
    )
    regular = classifier.classify(
        "chrome.exe",
        transient_title="ChatGPT apareceu numa pesquisa - Google Chrome",
    )
    assert recognized.source == "site_allowlist"
    assert recognized.site_key == "chatgpt"
    assert regular.classification == "neutral"
    assert regular.site_key is None


def test_manual_application_rule_has_priority_over_site():
    manual = SimpleNamespace(
        enabled=True,
        classification="neutral",
        category="other",
    )
    result = ApplicationClassifier(ContextRepository(manual=manual)).classify(
        "chrome.exe",
        transient_title="ChatGPT",
    )
    assert result.source == "manual_rule"
    assert result.classification == "neutral"


def test_known_project_is_saved_only_as_key():
    project = SimpleNamespace(
        id=7,
        project_key="condution_time",
        display_name="Condution Time",
        match_terms=json.dumps(["condution time", "condutiontime"]),
        classification="productive",
        category="programming",
    )
    result = ApplicationClassifier(ContextRepository(projects=[project])).classify(
        "code.exe",
        transient_title="arquivo-secreto.py - Condution Time - Visual Studio Code",
    )
    assert result.project_key == "condution_time"
    assert result.project_display_name == "Condution Time"
    assert not hasattr(result, "window_title")


def test_unknown_project_discards_title():
    result = ApplicationClassifier(ContextRepository()).classify(
        "code.exe",
        transient_title="arquivo-pessoal.py - Desconhecido - Visual Studio Code",
    )
    assert result.classification == "productive"
    assert result.project_key is None
    assert not hasattr(result, "window_title")


def test_aggregator_splits_blocks_by_site():
    persisted = []
    aggregator = ActivityAggregator(persisted.append, min_block_seconds=0)
    started = datetime.now(timezone.utc)
    app = ForegroundApplication(1, 1, "chrome.exe", "Google Chrome")
    classifier = ApplicationClassifier(ContextRepository())
    aggregator.observe(
        started,
        app,
        classifier.classify("chrome.exe"),
        None,
    )
    aggregator.observe(
        started + timedelta(seconds=5),
        app,
        classifier.classify("chrome.exe", transient_title="ChatGPT"),
        None,
    )
    aggregator.stop(started + timedelta(seconds=10))
    assert len(persisted) == 2
    assert persisted[0].site_key is None
    assert persisted[1].site_key == "chatgpt"


def test_project_api_crud(client, app):
    created = client.post(
        "/api/computer-monitor/projects",
        json={
            "display_name": "Projeto Teste",
            "match_terms": ["projeto teste"],
            "classification": "productive",
            "category": "programming",
        },
    )
    assert created.status_code == 201
    project_id = created.get_json()["project"]["id"]
    assert client.get("/api/computer-monitor/projects").status_code == 200
    updated = client.patch(
        f"/api/computer-monitor/projects/{project_id}",
        json={"enabled": False},
    )
    assert updated.get_json()["project"]["enabled"] is False
    assert client.delete(
        f"/api/computer-monitor/projects/{project_id}"
    ).status_code == 200


def test_project_api_rejects_short_terms(client):
    response = client.post(
        "/api/computer-monitor/projects",
        json={
            "display_name": "Teste",
            "match_terms": ["ab"],
            "classification": "productive",
            "category": "programming",
        },
    )
    assert response.status_code == 400


def test_study_xp_is_recalculable(app):
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
                record_origin="Estudo manual",
            )
        )
        db.session.commit()
        progress = rebuild_study_subject_progress()[0]
        assert progress.xp == 168  # 120 + 20 + 8 + bônus de foco limitado a 20
        assert progress.level == level_from_xp(168)
        rebuild_study_subject_progress()
        assert db.session.scalar(
            db.select(db.func.count(StudySubjectProgress.id))
        ) == 1


def test_profile_page_and_apis_work_without_data(client):
    assert client.get("/perfil").status_code == 200
    for endpoint in (
        "/api/profile",
        "/api/profile/study",
        "/api/profile/physical",
        "/api/profile/computer",
        "/api/profile/comparison",
    ):
        assert client.get(endpoint).status_code == 200


def test_computer_schema_has_no_private_content_columns(app):
    forbidden = {"window_title", "tab_title", "url", "document_name", "file_path"}
    assert forbidden.isdisjoint(ComputerActivityBlock.__table__.columns.keys())
