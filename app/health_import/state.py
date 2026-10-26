from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any


@dataclass
class HealthImportState:
    status: str = "disabled"
    last_file: str | None = None
    last_import_at: datetime | None = None
    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    recent_errors: list[str] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock, repr=False)

    def update(self, **changes: Any) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(self, key, value)

    def add_error(self, message: str) -> None:
        with self.lock:
            self.recent_errors = (self.recent_errors + [message])[-5:]
            self.status = "error"

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            payload = {
                "status": self.status,
                "last_file": self.last_file,
                "last_import_at": self.last_import_at,
                "imported_count": self.imported_count,
                "updated_count": self.updated_count,
                "skipped_count": self.skipped_count,
                "recent_errors": list(self.recent_errors),
            }
        if payload["last_import_at"]:
            payload["last_import_at"] = payload["last_import_at"].isoformat()
        return payload

