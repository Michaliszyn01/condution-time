from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from desktop.paths import get_desktop_config_path


@dataclass
class DesktopSettings:
    start_with_windows: bool = False
    start_minimized: bool = False
    open_at_startup: bool = True
    continue_in_tray: bool = True
    preferred_port: int = 5000
    window_width: int = 1440
    window_height: int = 900
    monitoring_enabled: bool = True
    start_monitoring_with_app: bool = True
    idle_threshold_seconds: int = 300
    sample_interval_seconds: int = 2
    health_import_enabled: bool = False
    health_import_folder: str = ""
    health_import_poll_seconds: int = 60
    health_import_stability_seconds: int = 20

    def normalized(self) -> "DesktopSettings":
        return DesktopSettings(
            start_with_windows=bool(self.start_with_windows),
            start_minimized=bool(self.start_minimized),
            open_at_startup=bool(self.open_at_startup),
            continue_in_tray=bool(self.continue_in_tray),
            preferred_port=min(max(int(self.preferred_port), 5000), 5010),
            window_width=min(max(int(self.window_width), 1100), 3840),
            window_height=min(max(int(self.window_height), 700), 2160),
            monitoring_enabled=bool(self.monitoring_enabled),
            start_monitoring_with_app=bool(self.start_monitoring_with_app),
            idle_threshold_seconds=min(
                max(int(self.idle_threshold_seconds), 60),
                7200,
            ),
            sample_interval_seconds=min(
                max(int(self.sample_interval_seconds), 1),
                10,
            ),
            health_import_enabled=bool(self.health_import_enabled),
            health_import_folder=str(self.health_import_folder or "").strip(),
            health_import_poll_seconds=min(
                max(int(self.health_import_poll_seconds), 30),
                3600,
            ),
            health_import_stability_seconds=min(
                max(int(self.health_import_stability_seconds), 5),
                120,
            ),
        )


class DesktopSettingsStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.path = path or get_desktop_config_path()
        self.logger = logger or logging.getLogger(__name__)

    def load(self) -> DesktopSettings:
        if not self.path.exists():
            return DesktopSettings()
        try:
            # utf-8-sig também aceita arquivos salvos pelo Windows PowerShell
            # com BOM, sem alterar a escrita canônica sem BOM.
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError("A configuração deve ser um objeto JSON.")
            allowed = {field.name for field in fields(DesktopSettings)}
            values = {key: value for key, value in payload.items() if key in allowed}
            return DesktopSettings(**values).normalized()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.logger.warning(
                "Configuração desktop inválida; usando valores padrão.",
                exc_info=True,
            )
            return DesktopSettings()

    def save(self, settings: DesktopSettings) -> DesktopSettings:
        normalized = settings.normalized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return normalized

    def update(self, changes: dict[str, Any]) -> DesktopSettings:
        allowed = {field.name for field in fields(DesktopSettings)}
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise ValueError(f"Configurações desconhecidas: {', '.join(unknown)}.")
        current = asdict(self.load())
        current.update(changes)
        return self.save(DesktopSettings(**current))
