from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.health_import.constants import ARCHIVE_SUFFIXES
from app.health_import.importer import HealthImporter
from app.health_import.state import HealthImportState


class HealthImportWatcher:
    def __init__(
        self,
        app: Any,
        settings_store: Any,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.app = app
        self.settings_store = settings_store
        self.logger = logger or logging.getLogger(__name__)
        self.state = HealthImportState()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._observed: dict[str, tuple[int, int]] = {}

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="health-import-watcher",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        self.thread = None

    def status(self) -> dict:
        return self.state.snapshot()

    def import_now(self) -> dict:
        settings = self.settings_store.load()
        source = self._latest_file(Path(settings.health_import_folder))
        if source is None:
            self.state.update(status="waiting_for_file")
            raise FileNotFoundError("Nenhuma exportação de saúde foi encontrada.")
        self.state.update(status="importing", last_file=source.name)
        try:
            result = HealthImporter(self.app).import_file(source)
            from datetime import datetime, timezone

            self.state.update(
                status="connected",
                last_import_at=datetime.now(timezone.utc),
                imported_count=result["imported"],
                updated_count=result["updated"],
                skipped_count=result["skipped"],
            )
            return result
        except Exception as exc:
            self.state.add_error(str(exc))
            raise

    def _run(self) -> None:
        while not self.stop_event.is_set():
            settings = self.settings_store.load()
            if not settings.health_import_enabled:
                self.state.update(status="disabled")
            else:
                folder = Path(settings.health_import_folder)
                source = self._latest_file(folder)
                if source is None:
                    self.state.update(status="waiting_for_file")
                elif self._is_stable(source):
                    try:
                        self.import_now()
                    except Exception:
                        self.logger.exception("Falha na importação automática de saúde.")
            self.stop_event.wait(max(1, settings.health_import_poll_seconds))

    def _is_stable(self, path: Path) -> bool:
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        key = str(path)
        previous = self._observed.get(key)
        self._observed[key] = current
        if previous != current:
            return False
        settings = self.settings_store.load()
        import time

        age = time.time() - stat.st_mtime
        if age < settings.health_import_stability_seconds:
            return False
        try:
            with path.open("rb") as file:
                file.read(1)
        except OSError:
            return False
        return True

    @staticmethod
    def _latest_file(folder: Path) -> Path | None:
        if not folder.is_dir():
            return None
        candidates = [
            path
            for path in folder.iterdir()
            if path.is_file()
            and (
                path.suffix.casefold() == ".zip"
                or path.name.casefold() == "health_connect_export.db"
            )
        ]
        return max(candidates, key=lambda path: path.stat().st_mtime, default=None)
