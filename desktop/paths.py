from __future__ import annotations

import os
import sys
from pathlib import Path

from desktop import APP_SLUG


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if is_frozen() and bundle_root:
        return Path(bundle_root).resolve()
    return get_project_root()


def resource_path(*parts: str) -> Path:
    return get_resource_root().joinpath(*parts)


def get_app_data_dir(*, create: bool = True) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    target = base / APP_SLUG
    if create:
        for child in ("data", "logs", "config", "backups"):
            (target / child).mkdir(parents=True, exist_ok=True)
    return target


def ensure_app_directories() -> Path:
    """Cria e retorna a raiz persistente usada pelo aplicativo desktop."""
    return get_app_data_dir(create=True)


def get_data_dir(*, create: bool = True) -> Path:
    target = get_app_data_dir(create=create) / "data"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_logs_dir(*, create: bool = True) -> Path:
    target = get_app_data_dir(create=create) / "logs"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_config_dir(*, create: bool = True) -> Path:
    target = get_app_data_dir(create=create) / "config"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_database_path() -> Path:
    return get_data_dir() / "condution_time.db"


def get_desktop_config_path() -> Path:
    return get_config_dir() / "desktop.json"


def get_runtime_state_path() -> Path:
    return get_config_dir() / "runtime.json"


def get_log_path() -> Path:
    return get_logs_dir() / "condution_time.log"


def get_icon_path() -> Path | None:
    candidate = resource_path("assets", "condution_time.ico")
    return candidate if candidate.is_file() else None


def sqlite_uri(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def get_startup_command(*, background: bool = True) -> list[str]:
    if is_frozen():
        command = [str(Path(sys.executable).resolve())]
    else:
        command = [sys.executable, "-m", "desktop.launcher"]
    if background:
        command.append("--background")
    return command
