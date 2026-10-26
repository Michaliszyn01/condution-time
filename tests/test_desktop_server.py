from app import create_app
from desktop.app_state import DesktopAppState
from desktop.server_manager import (
    ServerManager,
    ServerStartError,
    find_available_port,
    wait_until_ready,
)


def test_find_available_port_uses_next_candidate():
    port = find_available_port(
        5000,
        checker=lambda _host, candidate: candidate == 5002,
    )
    assert port == 5002


def test_find_available_port_stays_in_configured_attempts():
    try:
        find_available_port(5000, attempts=2, checker=lambda *_args: False)
    except ServerStartError as exc:
        assert "Nenhuma porta" in str(exc)
    else:
        raise AssertionError("A indisponibilidade deveria falhar.")


def test_find_available_port_rejects_privileged_port():
    try:
        find_available_port(80)
    except ValueError as exc:
        assert "1024" in str(exc)
    else:
        raise AssertionError("A porta deveria ser rejeitada.")


def test_wait_until_ready_returns_immediately_for_healthy_server():
    assert wait_until_ready(
        "http://127.0.0.1:5000/health",
        timeout=0.01,
        checker=lambda _url: True,
    )


class FakeServer:
    def __init__(self):
        self.ran = False
        self.closed = False

    def run(self):
        self.ran = True

    def close(self):
        self.closed = True


def test_server_manager_starts_on_loopback_and_stops(monkeypatch):
    state = DesktopAppState()
    fake_server = FakeServer()
    captured = {}

    def app_factory(config):
        captured.update(config)
        config = {
            **config,
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }
        return create_app(config)

    monkeypatch.setattr(
        "desktop.server_manager.find_available_port",
        lambda preferred: preferred,
    )
    manager = ServerManager(
        state,
        app_factory=app_factory,
        server_factory=lambda _app, host, port: (
            captured.update(host=host, port=port) or fake_server
        ),
        ready_waiter=lambda _url, timeout: True,
    )

    url = manager.start(
        preferred_port=5007,
        desktop_bridge=object(),
        run_migrations=False,
    )
    assert url == "http://127.0.0.1:5007"
    assert captured["host"] == "127.0.0.1"
    assert captured["DESKTOP_MODE"] is True
    assert state.server_active is True

    manager.stop()
    assert fake_server.closed is True
    assert state.server_active is False
