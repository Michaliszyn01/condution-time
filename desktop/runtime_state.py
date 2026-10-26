from __future__ import annotations

import ctypes
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from desktop.paths import get_runtime_state_path


RUNTIME_VERSION = "1"


@dataclass(frozen=True)
class RuntimeInfo:
    pid: int
    control_port: int
    started_at: str
    version: str = RUNTIME_VERSION

    @classmethod
    def create(cls, control_port: int) -> "RuntimeInfo":
        return cls(
            pid=os.getpid(),
            control_port=control_port,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_payload(cls, payload: Any) -> "RuntimeInfo":
        if not isinstance(payload, dict):
            raise ValueError("Estado de execução inválido.")
        try:
            info = cls(
                pid=int(payload["pid"]),
                control_port=int(payload["control_port"]),
                started_at=str(payload["started_at"]),
                version=str(payload["version"]),
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("Estado de execução incompleto.") from None
        if info.pid <= 0:
            raise ValueError("PID inválido.")
        if not 1024 <= info.control_port <= 65535:
            raise ValueError("Porta de controle inválida.")
        if info.version != RUNTIME_VERSION:
            raise ValueError("Versão de estado incompatível.")
        try:
            datetime.fromisoformat(info.started_at)
        except ValueError:
            raise ValueError("Data de início inválida.") from None
        return info


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


class RuntimeStateStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        logger: logging.Logger | None = None,
        process_checker: Callable[[int], bool] = pid_exists,
    ) -> None:
        self.path = path or get_runtime_state_path()
        self.logger = logger or logging.getLogger(__name__)
        self.process_checker = process_checker

    def load(self) -> RuntimeInfo | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return RuntimeInfo.from_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            self.logger.warning("runtime.json inválido; removendo estado obsoleto.")
            self.clear()
            return None

    def save(self, info: RuntimeInfo) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(info), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def is_process_alive(self, info: RuntimeInfo) -> bool:
        return self.process_checker(info.pid)

    def clear(
        self,
        *,
        expected_pid: int | None = None,
        expected_port: int | None = None,
    ) -> bool:
        if not self.path.exists():
            return False
        if expected_pid is not None or expected_port is not None:
            try:
                current = RuntimeInfo.from_payload(
                    json.loads(self.path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                current = None
            if current is not None:
                if expected_pid is not None and current.pid != expected_pid:
                    return False
                if expected_port is not None and current.control_port != expected_port:
                    return False
        try:
            self.path.unlink(missing_ok=True)
            return True
        except OSError:
            self.logger.warning("Não foi possível remover runtime.json.", exc_info=True)
            return False
