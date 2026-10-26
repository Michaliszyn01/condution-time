import json
from pathlib import Path

from desktop.config import DesktopSettings, DesktopSettingsStore
from desktop import paths


def test_app_data_structure_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    root = paths.get_app_data_dir()

    assert root == tmp_path / "CondutionTime"
    assert {item.name for item in root.iterdir()} == {
        "data",
        "logs",
        "config",
        "backups",
    }


def test_sqlite_uri_uses_absolute_forward_slash_path(tmp_path):
    uri = paths.sqlite_uri(tmp_path / "dados.db")
    assert uri.startswith("sqlite:///")
    assert uri.endswith("/dados.db")


def test_resource_path_uses_bundle_root_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("app", "static") == tmp_path / "app" / "static"


def test_startup_command_uses_module_in_development(monkeypatch):
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    command = paths.get_startup_command()
    assert command[1:3] == ["-m", "desktop.launcher"]
    assert command[-1] == "--background"


def test_settings_store_round_trip(tmp_path):
    store = DesktopSettingsStore(tmp_path / "desktop.json")
    saved = store.save(
        DesktopSettings(
            start_with_windows=True,
            preferred_port=5010,
            window_width=1500,
        )
    )
    assert saved == store.load()
    assert json.loads(store.path.read_text(encoding="utf-8"))["preferred_port"] == 5010


def test_settings_store_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "desktop.json"
    path.write_text("{invalid", encoding="utf-8")
    assert DesktopSettingsStore(path).load() == DesktopSettings()


def test_settings_are_normalized():
    settings = DesktopSettings(
        preferred_port=1,
        window_width=200,
        window_height=200,
    ).normalized()
    assert settings.preferred_port == 5000
    assert settings.window_width == 1100
    assert settings.window_height == 700


def test_settings_store_rejects_unknown_keys(tmp_path):
    store = DesktopSettingsStore(tmp_path / "desktop.json")
    try:
        store.update({"segredo": True})
    except ValueError as exc:
        assert "desconhecidas" in str(exc)
    else:
        raise AssertionError("A chave desconhecida deveria ser rejeitada.")


def test_app_factory_accepts_safe_instance_path(tmp_path):
    from app import create_app

    instance_path = tmp_path / "instance"
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "INSTANCE_PATH": str(instance_path),
        }
    )
    assert Path(application.instance_path) == instance_path.resolve()
    assert instance_path.is_dir()
