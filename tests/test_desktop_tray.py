import sys
from types import SimpleNamespace

from desktop.app_state import DesktopAppState
from desktop.tray import TrayController


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


class FakeMenuItem:
    def __init__(self, text, action, **options):
        self.text = text
        self.action = action
        self.options = options


class FakeIcon:
    def __init__(self, name, image, title, menu):
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.detached = False
        self.stopped = False
        self.menu_updates = 0

    def run_detached(self):
        self.detached = True

    def stop(self):
        self.stopped = True

    def update_menu(self):
        self.menu_updates += 1


class FakeBridge:
    def __init__(self):
        self.routes = []
        self.exits = 0

    def show_main_window(self, route):
        self.routes.append(route)

    def request_exit(self):
        self.exits += 1


def test_tray_uses_central_show_and_exit_actions(monkeypatch):
    fake_pystray = SimpleNamespace(
        Menu=FakeMenu,
        MenuItem=FakeMenuItem,
        Icon=FakeIcon,
    )
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    monkeypatch.setattr(TrayController, "_image", staticmethod(lambda: object()))

    state = DesktopAppState()
    bridge = FakeBridge()
    tray = TrayController(state, bridge)
    tray.start()

    assert tray.icon.detached is True
    assert state.tray_active is True

    actionable = [
        item
        for item in tray.icon.menu.items
        if isinstance(item, FakeMenuItem)
    ]
    actionable[0].action(None, None)
    actionable[1].action(None, None)
    actionable[2].action(None, None)
    actionable[3].action(None, None)
    actionable[-1].action(None, None)

    assert bridge.routes == ["/", "/registrar", "/sessao", "/historico"]
    assert bridge.exits == 1

    icon = tray.icon
    tray.stop()
    assert icon.stopped is True
    assert state.tray_active is False


def test_tray_exposes_monitor_status_and_pause_resume(monkeypatch):
    fake_pystray = SimpleNamespace(
        Menu=FakeMenu,
        MenuItem=FakeMenuItem,
        Icon=FakeIcon,
    )
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    monkeypatch.setattr(TrayController, "_image", staticmethod(lambda: object()))

    class Monitor:
        value = "running"

        def status(self):
            return {"status": self.value}

        def pause(self):
            self.value = "paused"

        def resume(self):
            self.value = "running"

        def start(self):
            self.value = "running"

    monitor = Monitor()
    tray = TrayController(DesktopAppState(), FakeBridge(), monitor_agent=monitor)
    tray.start()
    items = [
        item for item in tray.icon.menu.items if isinstance(item, FakeMenuItem)
    ]
    status_item = next(item for item in items if callable(item.text) and item.action is None)
    action_item = next(item for item in items if item.action == tray._toggle_monitor)
    assert status_item.text() == "Status: monitorando"
    assert action_item.text() == "Pausar monitoramento"
    action_item.action(None, None)
    assert monitor.value == "paused"
    assert action_item.text() == "Retomar monitoramento"
