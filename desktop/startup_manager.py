from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from desktop import APP_SLUG
from desktop.paths import get_startup_command


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _registry(registry: Any | None = None) -> Any:
    if registry is not None:
        return registry
    if os.name != "nt":
        raise OSError("Inicialização automática está disponível apenas no Windows.")
    import winreg

    return winreg


def startup_command() -> str:
    return subprocess.list2cmdline(get_startup_command(background=True))


def enable_startup(*, registry: Any | None = None) -> None:
    winreg = _registry(registry)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, APP_SLUG, 0, winreg.REG_SZ, startup_command())


def disable_startup(*, registry: Any | None = None) -> None:
    winreg = _registry(registry)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, APP_SLUG)
    except FileNotFoundError:
        return


def is_startup_enabled(*, registry: Any | None = None) -> bool:
    try:
        winreg = _registry(registry)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_READ,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, APP_SLUG)
        return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_startup_enabled(
    enabled: bool,
    *,
    registry: Any | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    logger = logger or logging.getLogger(__name__)
    try:
        if enabled:
            enable_startup(registry=registry)
        else:
            disable_startup(registry=registry)
        return is_startup_enabled(registry=registry)
    except OSError:
        logger.exception("Falha ao atualizar inicialização com o Windows.")
        raise

