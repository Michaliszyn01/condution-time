from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class ForegroundApplication:
    hwnd: int
    pid: int
    executable_name: str
    friendly_name: str


@dataclass(frozen=True)
class Classification:
    classification: str
    category: str
    source: str
    project_rule_id: int | None = None
    project_key: str | None = None
    project_display_name: str | None = None
    site_key: str | None = None
    context_source: str | None = None


@dataclass(frozen=True)
class SessionContext:
    id: int
    session_type: str
    related_category: str


@dataclass
class BlockDraft:
    record_date: Any
    executable_name: str | None
    friendly_name: str | None
    classification: str
    category: str
    classification_source: str
    started_at: datetime
    ended_at: datetime | None = None
    was_idle: bool = False
    session_id: int | None = None
    project_rule_id: int | None = None
    project_key: str | None = None
    project_display_name: str | None = None
    site_key: str | None = None
    context_source: str | None = None

    def key(self) -> tuple[Any, ...]:
        return (
            self.record_date,
            self.executable_name,
            self.classification,
            self.category,
            self.classification_source,
            self.was_idle,
            self.session_id,
            self.project_key,
            self.site_key,
        )


@dataclass
class MonitorRuntimeState:
    status: str = "stopped"
    paused: bool = False
    current_process: str | None = None
    current_project: str | None = None
    current_site: str | None = None
    current_block_started_at: datetime | None = None
    last_capture_at: datetime | None = None
    idle_seconds: float = 0
    recent_errors: list[str] = field(default_factory=list)
    blocks_persisted: int = 0
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
                "paused": self.paused,
                "current_process": self.current_process,
                "current_project": self.current_project,
                "current_site": self.current_site,
                "current_block_started_at": self.current_block_started_at,
                "last_capture_at": self.last_capture_at,
                "idle_seconds": self.idle_seconds,
                "recent_errors": list(self.recent_errors),
                "blocks_persisted": self.blocks_persisted,
            }
        for key in ("current_block_started_at", "last_capture_at"):
            if payload[key] is not None:
                payload[key] = payload[key].isoformat()
        return payload
