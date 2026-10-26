import json
import logging
from dataclasses import replace

import pytest

from desktop.app_state import DesktopAppState
from desktop.bridge import DesktopBridge
from desktop.config import DesktopSettingsStore
from desktop.ipc_client import IpcClient, command_request, send_request
from desktop.ipc_server import IpcServer
from desktop.runtime_state import RuntimeInfo, RuntimeStateStore


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, interval):
        self.value += interval


class SequenceStore:
    def __init__(self, values, *, alive=True):
        self.values = list(values)
        self.last = self.values[-1] if self.values else None
        self.alive = alive
        self.cleared = []

    def load(self):
        if self.values:
            self.last = self.values.pop(0)
        return self.last

    def is_process_alive(self, _info):
        return self.alive

    def clear(self, **kwargs):
        self.cleared.append(kwargs)
        return True


def test_runtime_state_round_trip(tmp_path):
    store = RuntimeStateStore(
        tmp_path / "runtime.json",
        process_checker=lambda pid: pid == 123,
    )
    info = RuntimeInfo(
        pid=123,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    store.save(info)
    assert store.load() == info
    assert store.is_process_alive(info) is True


def test_runtime_state_corrupt_is_removed(tmp_path):
    path = tmp_path / "runtime.json"
    path.write_text("{corrompido", encoding="utf-8")
    store = RuntimeStateStore(path)
    assert store.load() is None
    assert path.exists() is False


@pytest.mark.parametrize(
    "changes",
    [
        {"pid": 0},
        {"control_port": 80},
        {"started_at": "ontem"},
        {"version": "99"},
    ],
)
def test_runtime_state_rejects_invalid_fields(changes):
    payload = {
        "pid": 123,
        "control_port": 5015,
        "started_at": "2026-07-28T12:00:00+00:00",
        "version": "1",
        **changes,
    }
    with pytest.raises(ValueError):
        RuntimeInfo.from_payload(payload)


def test_runtime_clear_does_not_remove_newer_instance(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime.json")
    current = RuntimeInfo(
        pid=222,
        control_port=5016,
        started_at="2026-07-28T12:00:00+00:00",
    )
    store.save(current)
    assert store.clear(expected_pid=111, expected_port=5015) is False
    assert store.load() == current


def test_ipc_server_accepts_only_known_commands(tmp_path):
    actions = []
    store = RuntimeStateStore(
        tmp_path / "runtime.json",
        process_checker=lambda _pid: True,
    )
    server = IpcServer(
        lambda action, route: actions.append((action, route)) or True,
        state_store=store,
    )
    info = server.start()
    try:
        assert send_request(info, {"command": "ping"}) == {
            "success": True,
            "action": "ping",
        }
        assert send_request(info, {"command": "show_window"})["success"] is True
        response = send_request(
            info,
            {"command": "navigate", "route": "/registrar"},
        )
        assert response == {"success": True, "action": "navigate:/registrar"}
        denied = send_request(
            info,
            {"command": "navigate", "route": "https://example.com"},
        )
        assert denied["success"] is False
        assert actions == [
            ("show_window", None),
            ("navigate", "/registrar"),
        ]
    finally:
        server.stop()


def test_ipc_shutdown_removes_runtime_file(tmp_path):
    path = tmp_path / "runtime.json"
    server = IpcServer(
        lambda _action, _route: True,
        state_store=RuntimeStateStore(path),
    )
    server.start()
    assert path.exists()
    server.stop()
    assert path.exists() is False


def test_client_pings_then_delivers_show_window():
    info = RuntimeInfo(
        pid=123,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    requests = []

    def sender(_info, request):
        requests.append(request)
        return {"success": True, "action": request["command"]}

    client = IpcClient(
        state_store=SequenceStore([info]),
        sender=sender,
    )
    assert client.deliver(timeout=0.1) is True
    assert requests == [{"command": "ping"}, {"command": "show_window"}]


def test_client_delivers_allowed_route():
    info = RuntimeInfo(
        pid=123,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    requests = []

    def sender(_info, request):
        requests.append(request)
        return {"success": True}

    client = IpcClient(state_store=SequenceStore([info]), sender=sender)
    assert client.deliver(route="/sessao", timeout=0.1) is True
    assert requests[-1] == {"command": "navigate", "route": "/sessao"}


def test_client_retries_while_first_instance_starts():
    info = RuntimeInfo(
        pid=123,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    clock = FakeClock()
    store = SequenceStore([None, None, info])
    client = IpcClient(
        state_store=store,
        sender=lambda _info, request: {
            "success": True,
            "action": request["command"],
        },
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    assert client.deliver(timeout=1.0, interval=0.2) is True
    assert clock.value == pytest.approx(0.4)


def test_client_retries_temporary_ipc_failure():
    info = RuntimeInfo(
        pid=123,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    clock = FakeClock()
    attempts = {"count": 0}

    def sender(_info, request):
        if request["command"] == "ping":
            attempts["count"] += 1
            if attempts["count"] < 3:
                return None
        return {"success": True, "action": request["command"]}

    client = IpcClient(
        state_store=SequenceStore([info]),
        sender=sender,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    assert client.deliver(timeout=1.0, interval=0.2) is True
    assert attempts["count"] == 3


def test_client_clears_missing_pid_and_times_out():
    info = RuntimeInfo(
        pid=999999,
        control_port=5015,
        started_at="2026-07-28T12:00:00+00:00",
    )
    clock = FakeClock()
    store = SequenceStore([info], alive=False)
    client = IpcClient(
        state_store=store,
        sender=lambda *_args: None,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    assert client.deliver(timeout=0.5, interval=0.2) is False
    assert store.cleared


def test_forbidden_route_is_rejected_before_socket():
    with pytest.raises(ValueError):
        command_request("https://example.com")


class ReadyWindow:
    def __init__(self):
        self.calls = []

    def load_url(self, url):
        self.calls.append(("load", url))

    def show(self):
        self.calls.append(("show", None))

    def restore(self):
        self.calls.append(("restore", None))

    def bring_to_front(self):
        self.calls.append(("front", None))


def test_show_command_during_startup_runs_after_window_loaded(tmp_path):
    state = DesktopAppState(port=5000)
    focused = []
    bridge = DesktopBridge(
        state,
        DesktopSettingsStore(tmp_path / "desktop.json"),
        startup_checker=lambda: False,
        window_focuser=lambda window: focused.append(window) or True,
    )
    assert bridge.show_main_window("/historico") is True
    window = ReadyWindow()
    bridge.set_window(window)
    assert window.calls == []
    bridge.mark_window_ready()
    assert ("load", "http://127.0.0.1:5000/historico") in window.calls
    assert ("show", None) in window.calls
    assert focused == [window]
