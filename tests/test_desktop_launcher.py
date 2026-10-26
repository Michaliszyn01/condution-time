import argparse
import logging

import pytest

from desktop.config import DesktopSettings
from desktop.launcher import parse_args, should_hide_window, valid_port
import desktop.launcher as launcher


def test_launcher_defaults():
    args = parse_args([])
    assert args.background is False
    assert args.force_open is False
    assert args.no_tray is False
    assert args.port is None


def test_launcher_accepts_all_runtime_flags():
    args = parse_args(
        [
            "--background",
            "--open",
            "--no-tray",
            "--port",
            "5009",
            "--route",
            "/registrar",
        ]
    )
    assert args.background is True
    assert args.force_open is True
    assert args.no_tray is True
    assert args.port == 5009
    assert args.route == "/registrar"


def test_background_hides_window_when_tray_is_available():
    args = parse_args(["--background"])
    assert should_hide_window(args, DesktopSettings(), use_tray=True) is True


def test_open_and_no_tray_keep_window_visible():
    settings = DesktopSettings(start_minimized=True, open_at_startup=False)
    assert should_hide_window(parse_args(["--open"]), settings, True) is False
    assert should_hide_window(parse_args(["--no-tray"]), settings, False) is False


def test_internal_route_keeps_window_visible():
    settings = DesktopSettings(start_minimized=True)
    assert (
        should_hide_window(parse_args(["--route", "/historico"]), settings, True)
        is False
    )


def test_launcher_rejects_external_route():
    with pytest.raises(SystemExit):
        parse_args(["--route", "https://example.com"])


class ExistingInstance:
    def acquire(self):
        return False


def test_second_execution_delivers_show_and_exits_successfully(monkeypatch):
    delivered = []
    messages = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def deliver(self, *, route=None):
            delivered.append(route)
            return True

    monkeypatch.setattr(launcher, "configure_logging", lambda: logging.getLogger())
    monkeypatch.setattr(launcher, "RuntimeStateStore", lambda **_kwargs: object())
    monkeypatch.setattr(launcher, "IpcClient", FakeClient)
    monkeypatch.setattr(
        launcher,
        "show_already_running_message",
        messages.append,
    )
    result = launcher.run_desktop(
        parse_args(["--route", "/registrar"]),
        instance=ExistingInstance(),
    )
    assert result == 0
    assert delivered == ["/registrar"]
    assert messages == []


def test_second_execution_shows_error_only_after_ipc_failure(monkeypatch):
    messages = []

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def deliver(self, *, route=None):
            return False

    monkeypatch.setattr(launcher, "configure_logging", lambda: logging.getLogger())
    monkeypatch.setattr(launcher, "RuntimeStateStore", lambda **_kwargs: object())
    monkeypatch.setattr(launcher, "IpcClient", FailingClient)
    monkeypatch.setattr(
        launcher,
        "show_already_running_message",
        messages.append,
    )
    result = launcher.run_desktop(parse_args([]), instance=ExistingInstance())
    assert result == 2
    assert len(messages) == 1
    assert "não foi possível restaurar" in messages[0]


@pytest.mark.parametrize("value", ["0", "1023", "65536", "texto"])
def test_launcher_rejects_invalid_port(value):
    with pytest.raises(argparse.ArgumentTypeError):
        valid_port(value)
