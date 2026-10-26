from app import create_app
from desktop.app_state import DesktopAppState
from desktop.bridge import DesktopBridge
from desktop.config import DesktopSettingsStore


class FakeWindow:
    def __init__(self):
        self.calls = []

    def show(self):
        self.calls.append("show")

    def restore(self):
        self.calls.append("restore")

    def bring_to_front(self):
        self.calls.append("front")

    def load_url(self, url):
        self.calls.append(url)


def make_bridge(tmp_path, **kwargs):
    state = DesktopAppState(port=5004, server_active=True)
    store = DesktopSettingsStore(tmp_path / "desktop.json")
    return DesktopBridge(
        state,
        store,
        startup_checker=lambda: False,
        **kwargs,
    )


def test_bridge_navigates_only_known_routes(tmp_path):
    bridge = make_bridge(tmp_path)
    window = FakeWindow()
    bridge.set_window(window)
    bridge.mark_window_ready()
    assert bridge.navigate("/historico") is True
    assert "http://127.0.0.1:5004/historico" in window.calls

    try:
        bridge.navigate("https://example.com")
    except ValueError as exc:
        assert "não permitida" in str(exc)
    else:
        raise AssertionError("URL externa deveria ser rejeitada.")


def test_bridge_opens_only_known_directories(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    bridge = make_bridge(tmp_path, folder_opener=opened.append)
    assert bridge.open_data_folder()
    assert bridge.open_logs_folder()
    assert [path.rsplit("\\", 1)[-1] for path in opened] == ["data", "logs"]


def test_bridge_updates_startup_and_port(tmp_path):
    bridge = make_bridge(
        tmp_path,
        startup_setter=lambda enabled: enabled,
    )
    payload = bridge.update_settings(
        {"start_with_windows": True, "preferred_port": 5010}
    )
    assert payload["start_with_windows"] is True
    assert payload["preferred_port"] == 5010


def test_bridge_rejects_unknown_setting(tmp_path):
    bridge = make_bridge(tmp_path)
    try:
        bridge.update_settings({"monitoring": True})
    except ValueError as exc:
        assert "não permitidas" in str(exc)
    else:
        raise AssertionError("A configuração deveria ser rejeitada.")


def test_bridge_requests_shutdown_once_callback_is_available(tmp_path):
    calls = []
    bridge = make_bridge(tmp_path, shutdown_callback=lambda: calls.append("exit"))
    bridge.request_exit()
    assert calls == ["exit"]


def test_desktop_api_is_unavailable_in_browser_mode(client):
    response = client.get("/api/desktop/settings")
    assert response.status_code == 503
    assert "indisponíveis" in response.get_json()["error"]


class FakeBridge:
    exit_requested = False

    def get_settings(self):
        return {"preferred_port": 5000, "server_active": True}

    def update_settings(self, payload):
        if "bad" in payload:
            raise ValueError("inválido")
        return payload

    def open_data_folder(self):
        return True

    def open_logs_folder(self):
        return True

    def request_exit(self):
        self.exit_requested = True


def desktop_client():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "DESKTOP_MODE": True,
            "DESKTOP_BRIDGE": FakeBridge(),
        }
    )
    return app.test_client()


def test_desktop_api_reads_and_updates_settings():
    client = desktop_client()
    assert client.get("/api/desktop/settings").get_json()["server_active"] is True
    response = client.patch(
        "/api/desktop/settings",
        json={"preferred_port": 5008},
    )
    assert response.status_code == 200
    assert response.get_json()["preferred_port"] == 5008


def test_desktop_api_validates_payload():
    response = desktop_client().patch(
        "/api/desktop/settings",
        data="[]",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_desktop_api_opens_known_folders():
    client = desktop_client()
    assert client.post("/api/desktop/open-data-folder").get_json() == {"ok": True}
    assert client.post("/api/desktop/open-logs-folder").get_json() == {"ok": True}


def test_desktop_api_uses_central_exit_bridge():
    client = desktop_client()
    assert client.post("/api/desktop/exit").get_json() == {"ok": True}


def test_health_is_public_and_minimal(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_settings_page_keeps_desktop_section_in_browser_mode(client):
    response = client.get("/configuracoes")
    assert response.status_code == 200
    assert "Iniciar com o Windows" in response.get_data(as_text=True)
