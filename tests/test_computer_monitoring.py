from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import ApplicationRule, ComputerActivityBlock, StudyRecord
from app.services.computer_service import (
    create_application_rule,
    delete_all_computer_data,
    get_computer_summary_for_date,
    summarize_blocks,
)
from desktop.monitoring.aggregator import ActivityAggregator
from desktop.monitoring.agent import ComputerMonitorAgent
from desktop.monitoring.classifier import ApplicationClassifier
from desktop.monitoring.foreground import (
    ForegroundCapture,
    normalize_executable_name,
)
from desktop.monitoring.idle import get_idle_seconds
from desktop.monitoring.state import (
    Classification,
    ForegroundApplication,
    SessionContext,
)


UTC = timezone.utc


class RuleRepository:
    def __init__(self, rule=None):
        self.rule = rule

    def get_application_rule(self, _executable_name):
        return self.rule


def app_info(executable="code.exe"):
    return ForegroundApplication(10, 42, executable, executable)


def classification(value="productive", category="programming", source="default_rule"):
    return Classification(value, category, source)


def block(target_date, seconds, value="productive", source="default_rule", **kwargs):
    started = datetime.combine(target_date, datetime.min.time(), UTC)
    return ComputerActivityBlock(
        record_date=target_date,
        executable_name=None if kwargs.get("was_idle") else kwargs.get("executable", "code.exe"),
        friendly_name=None if kwargs.get("was_idle") else "Visual Studio Code",
        classification="neutral" if kwargs.get("was_idle") else value,
        category="system" if kwargs.get("was_idle") else kwargs.get("category", "programming"),
        classification_source="fallback" if kwargs.get("was_idle") else source,
        started_at=started,
        ended_at=started + timedelta(seconds=seconds),
        duration_seconds=seconds,
        was_idle=bool(kwargs.get("was_idle")),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Code.exe", "code.exe"),
        ("C:\\Apps\\RocketLeague.exe", "rocketleague.exe"),
        (" chrome.exe ", "chrome.exe"),
        ("", None),
    ],
)
def test_normalize_executable_name(raw, expected):
    assert normalize_executable_name(raw) == expected


def test_foreground_capture_handles_process_ending(monkeypatch):
    import desktop.monitoring.foreground as foreground

    class NoSuchProcess(Exception):
        pass

    fake_psutil = SimpleNamespace(
        NoSuchProcess=NoSuchProcess,
        AccessDenied=type("AccessDenied", (Exception,), {}),
        ZombieProcess=type("ZombieProcess", (Exception,), {}),
        Process=lambda _pid: (_ for _ in ()).throw(NoSuchProcess()),
    )

    class User32:
        @staticmethod
        def GetForegroundWindow():
            return 99

        @staticmethod
        def GetWindowThreadProcessId(_hwnd, pointer):
            pointer._obj.value = 55

    monkeypatch.setattr(foreground.sys, "platform", "win32")
    monkeypatch.setattr(foreground.ctypes, "windll", SimpleNamespace(user32=User32()))
    assert ForegroundCapture(psutil_module=fake_psutil).capture() is None


def test_idle_detection_uses_only_elapsed_input_time():
    def reader(info):
        info.dwTime = 1_000
        return True

    assert get_idle_seconds(last_input_reader=reader, tick_reader=lambda: 6_500) == 5.5


def test_default_manual_browser_and_session_classification():
    classifier = ApplicationClassifier(RuleRepository())
    assert classifier.classify("code.exe").classification == "productive"
    browser = classifier.classify("chrome.exe")
    assert (browser.classification, browser.category) == ("neutral", "other")
    ignored = classifier.classify("explorer.exe")
    assert ignored.classification == "ignored"

    session = SessionContext(1, "study", "study")
    contextual = classifier.classify("chrome.exe", session)
    assert contextual == Classification("productive", "study", "session_context")

    manual = SimpleNamespace(
        enabled=True,
        classification="distracting",
        category="social",
    )
    classifier = ApplicationClassifier(RuleRepository(manual))
    result = classifier.classify("chrome.exe", session)
    assert result == Classification("distracting", "social", "manual_rule")


def test_aggregator_groups_switches_and_discards_short_noise():
    persisted = []
    aggregator = ActivityAggregator(persisted.append)
    start = datetime(2026, 7, 28, 12, tzinfo=UTC)
    aggregator.observe(start, app_info(), classification(), None)
    aggregator.observe(start + timedelta(seconds=2), app_info(), classification(), None)
    aggregator.observe(
        start + timedelta(seconds=4),
        app_info("chrome.exe"),
        classification("neutral", "other"),
        None,
    )
    assert len(persisted) == 1
    assert persisted[0].executable_name == "code.exe"
    assert (persisted[0].ended_at - persisted[0].started_at).total_seconds() == 4

    aggregator.stop(start + timedelta(seconds=6))
    assert len(persisted) == 1


def test_aggregator_idle_gap_pause_and_resume_boundaries():
    persisted = []
    aggregator = ActivityAggregator(persisted.append, min_block_seconds=1)
    start = datetime(2026, 7, 28, 12, tzinfo=UTC)
    aggregator.observe(start, app_info(), classification(), None)
    aggregator.observe(
        start + timedelta(seconds=305),
        None,
        None,
        None,
        idle_seconds=300,
        idle_threshold_seconds=300,
    )
    aggregator.observe(
        start + timedelta(seconds=310),
        app_info(),
        classification(),
        None,
        idle_seconds=0,
    )
    assert persisted[-1].was_idle is True
    assert persisted[-1].executable_name is None
    aggregator.pause(start + timedelta(seconds=315))
    assert persisted[-1].executable_name == "code.exe"


def test_aggregator_splits_day_and_does_not_attribute_long_gap():
    persisted = []
    aggregator = ActivityAggregator(persisted.append, min_block_seconds=1)
    start = datetime(2026, 7, 29, 2, 59, 58, tzinfo=UTC)
    aggregator.observe(start, app_info(), classification(), None)
    aggregator.observe(start + timedelta(seconds=4), app_info(), classification(), None)
    assert persisted[0].record_date == date(2026, 7, 28)
    aggregator.observe(start + timedelta(seconds=40), app_info(), classification(), None)
    assert aggregator.current.started_at == start + timedelta(seconds=40)


def test_summary_requires_five_minutes_and_counts_coverage(app):
    target = date(2026, 7, 28)
    with app.app_context():
        low = summarize_blocks([block(target, 299)])
        assert low["score"]["evaluated"] is False

        summary = summarize_blocks(
            [
                block(target, 300),
                block(target, 100, value="neutral"),
                block(target, 100, value="neutral", source="fallback", executable="unknown.exe"),
                block(target, 60, was_idle=True),
            ]
        )
        assert summary["score"]["evaluated"] is True
        assert summary["idle_seconds"] == 60
        assert summary["classified_apps_percentage"] == 80


def test_application_rule_is_case_insensitive_and_rejects_paths(app):
    with app.app_context():
        created = create_application_rule(
            {
                "executable_name": "code.exe",
                "classification": "productive",
                "category": "programming",
            }
        )
        assert created["executable_name"] == "code.exe"
        with pytest.raises(ValueError):
            create_application_rule(
                {
                    "executable_name": "C:\\Apps\\code.exe",
                    "classification": "productive",
                    "category": "programming",
                }
            )
        with pytest.raises(ValueError):
            create_application_rule(
                {
                    "executable_name": "CODE.EXE",
                    "classification": "productive",
                    "category": "programming",
                }
            )


def test_clear_data_preserves_other_records(app):
    target = date(2026, 7, 28)
    with app.app_context():
        db.session.add(block(target, 300))
        db.session.add(
            StudyRecord(
                record_date=target,
                subject="Teste",
                topic="Persistência",
                duration_minutes=30,
                focus_quality="good",
                record_origin="manual",
            )
        )
        db.session.commit()
        assert delete_all_computer_data() == 1
        assert db.session.scalar(db.select(db.func.count(StudyRecord.id))) == 1


def test_monitor_api_rules_summary_clear_and_local_only(client, app):
    target = date.today()
    with app.app_context():
        db.session.add(block(target, 300))
        db.session.commit()

    created = client.post(
        "/api/computer-monitor/rules",
        json={
            "executable_name": "code.exe",
            "classification": "productive",
            "category": "programming",
        },
    )
    assert created.status_code == 201
    rule_id = created.get_json()["rule"]["id"]
    assert client.get("/api/computer-monitor/rules").get_json()["rules"]
    assert client.patch(
        f"/api/computer-monitor/rules/{rule_id}",
        json={"category": "work"},
    ).status_code == 200
    assert client.get("/api/computer-monitor/today-summary").status_code == 200
    assert client.post(
        "/api/computer-monitor/clear-data",
        json={"confirm": False},
    ).status_code == 400
    assert client.delete(f"/api/computer-monitor/rules/{rule_id}").status_code == 200
    assert client.get(
        "/api/computer-monitor/status",
        environ_base={"REMOTE_ADDR": "10.0.0.2"},
    ).status_code == 403


class AgentRepository:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.saved = []

    def get_application_rule(self, _name):
        return None

    def get_active_session(self, _target_date):
        if self.fail:
            raise RuntimeError("database unavailable")
        return None

    def save_block(self, draft):
        self.saved.append(draft)
        return draft


def test_agent_pause_resume_stop_and_capture_error(app):
    repository = AgentRepository()
    agent = ComputerMonitorAgent(
        app,
        capture=SimpleNamespace(capture=lambda: app_info()),
        idle_reader=lambda: 0,
        repository=repository,
    )
    agent._sample_once()
    assert agent.status()["current_process"] == "code.exe"
    assert agent.start() is True
    assert agent.pause() is True
    assert agent.status()["status"] == "paused"
    assert agent.resume() is True
    assert agent.stop() is True
    assert agent.status()["status"] == "stopped"

    failing = ComputerMonitorAgent(
        app,
        capture=SimpleNamespace(capture=lambda: app_info()),
        idle_reader=lambda: 0,
        repository=AgentRepository(fail=True),
    )
    failing._sample_once()
    assert failing.status()["status"] == "error"
    assert failing.status()["recent_errors"] == ["RuntimeError"]


def test_computer_pages_use_real_empty_state(client):
    computer = client.get("/computador")
    settings = client.get("/configuracoes")
    assert computer.status_code == 200
    assert settings.status_code == 200
    assert "3h 42min" not in computer.text
    assert "Regras de aplicativos" in computer.text
    assert "cdn.jsdelivr.net" not in computer.text
    assert "computer-local-chart" in computer.text
    assert "Não registrados:" in settings.text
