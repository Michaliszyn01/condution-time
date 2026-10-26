from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class DesktopAppState:
    port: int | None = None
    server_active: bool = False
    tray_active: bool = False
    shutting_down: bool = False
    window: Any = None
    window_ready: bool = False
    pending_route: str | None = None
    window_show_requested: bool = False
    lock: RLock = field(default_factory=RLock, repr=False)

    @property
    def base_url(self) -> str | None:
        return f"http://127.0.0.1:{self.port}" if self.port else None

    def begin_shutdown(self) -> bool:
        with self.lock:
            if self.shutting_down:
                return False
            self.shutting_down = True
            return True

    def request_window(self, route: str | None = None) -> None:
        with self.lock:
            self.window_show_requested = True
            if route is not None:
                self.pending_route = route

    def mark_window_ready(self) -> tuple[bool, str | None]:
        with self.lock:
            self.window_ready = True
            requested = self.window_show_requested
            route = self.pending_route
            self.window_show_requested = False
            self.pending_route = None
            return requested, route

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "port": self.port,
                "server_active": self.server_active,
                "tray_active": self.tray_active,
                "shutting_down": self.shutting_down,
                "window_ready": self.window_ready,
                "base_url": self.base_url,
            }
