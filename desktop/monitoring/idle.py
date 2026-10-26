from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def get_idle_seconds(
    *,
    last_input_reader: Callable[[LASTINPUTINFO], bool] | None = None,
    tick_reader: Callable[[], int] | None = None,
) -> float:
    if sys.platform != "win32" and last_input_reader is None:
        return 0.0
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    reader = last_input_reader or (
        lambda target: bool(ctypes.windll.user32.GetLastInputInfo(ctypes.byref(target)))
    )
    if not reader(info):
        raise OSError("GetLastInputInfo não respondeu.")
    ticks = tick_reader or ctypes.windll.kernel32.GetTickCount64
    elapsed_ms = max(0, int(ticks()) - int(info.dwTime))
    return elapsed_ms / 1000
