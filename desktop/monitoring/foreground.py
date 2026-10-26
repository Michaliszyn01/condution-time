from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Any

from desktop.monitoring.constants import (
    DEFAULT_RULES,
    PROJECT_CAPABLE_EXECUTABLES,
    SITE_CAPABLE_EXECUTABLES,
)
from desktop.monitoring.state import ForegroundApplication


def normalize_executable_name(value: str | None) -> str | None:
    if not value:
        return None
    name = Path(value).name.strip().lower()
    return name or None


def friendly_name_for(executable_name: str) -> str:
    default = DEFAULT_RULES.get(executable_name)
    if default:
        return default[0]
    stem = Path(executable_name).stem
    return stem.replace("-", " ").replace("_", " ").strip().title() or executable_name


class ForegroundCapture:
    def __init__(self, *, psutil_module: Any | None = None) -> None:
        self._psutil = psutil_module

    def capture(self) -> ForegroundApplication | None:
        if sys.platform != "win32":
            return None
        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow())
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None

        psutil = self._psutil
        if psutil is None:
            import psutil as imported_psutil

            psutil = imported_psutil
        try:
            process = psutil.Process(int(pid.value))
            executable_name = normalize_executable_name(process.name())
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
            OSError,
        ):
            return None
        if executable_name is None:
            return None
        return ForegroundApplication(
            hwnd=hwnd,
            pid=int(pid.value),
            executable_name=executable_name,
            friendly_name=friendly_name_for(executable_name),
        )

    @staticmethod
    def capture_context_title(app: ForegroundApplication) -> str | None:
        """Lê o título apenas para apps allowlisted; o chamador deve descartá-lo."""
        if sys.platform != "win32" or app.executable_name not in (
            PROJECT_CAPABLE_EXECUTABLES | SITE_CAPABLE_EXECUTABLES
        ):
            return None
        length = int(ctypes.windll.user32.GetWindowTextLengthW(app.hwnd))
        if length <= 0 or length > 1000:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = ctypes.windll.user32.GetWindowTextW(
            app.hwnd,
            buffer,
            length + 1,
        )
        return buffer.value if copied else None
