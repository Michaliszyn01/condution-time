from __future__ import annotations

import ctypes
import os
from typing import Any

from desktop import APP_MUTEX_NAME


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(
        self,
        name: str = APP_MUTEX_NAME,
        *,
        kernel32: Any | None = None,
    ) -> None:
        self.name = name
        self.kernel32 = kernel32
        self.handle: Any | None = None
        self.already_running = False

    def acquire(self) -> bool:
        if self.handle is not None:
            return not self.already_running
        if os.name != "nt" and self.kernel32 is None:
            self.handle = object()
            self.already_running = False
            return True
        kernel32 = self.kernel32 or ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, True, self.name)
        if not handle:
            raise OSError("Não foi possível criar o mutex da aplicação.")
        self.handle = handle
        self.already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
        if self.already_running:
            kernel32.CloseHandle(handle)
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        if os.name == "nt" or self.kernel32 is not None:
            kernel32 = self.kernel32 or ctypes.windll.kernel32
            kernel32.ReleaseMutex(self.handle)
            kernel32.CloseHandle(self.handle)
        self.handle = None
        self.already_running = False

    def __enter__(self) -> "SingleInstance":
        self.acquire()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.release()


def show_already_running_message(
    message: str = "Condution Time já está em execução.",
) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "Condution Time",
            0x00000040,
        )
    except OSError:
        pass
