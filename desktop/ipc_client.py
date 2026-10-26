from __future__ import annotations

import json
import logging
import socket
import time
import ctypes
import os
from collections.abc import Callable
from typing import Any

from desktop.bridge import ALLOWED_ROUTES
from desktop.ipc_server import CONTROL_HOST, MAX_MESSAGE_BYTES
from desktop.runtime_state import RuntimeInfo, RuntimeStateStore


def send_request(
    info: RuntimeInfo,
    request: dict[str, Any],
    *,
    timeout: float = 0.75,
) -> dict[str, Any] | None:
    try:
        with socket.create_connection(
            (CONTROL_HOST, info.control_port),
            timeout=timeout,
        ) as connection:
            connection.settimeout(timeout)
            connection.sendall(
                json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
            )
            response = connection.recv(MAX_MESSAGE_BYTES + 1)
        if len(response) > MAX_MESSAGE_BYTES:
            return None
        payload = json.loads(response.decode("utf-8").strip())
        return payload if isinstance(payload, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def command_request(route: str | None = None) -> dict[str, str]:
    if route is None:
        return {"command": "show_window"}
    if route not in ALLOWED_ROUTES:
        raise ValueError("Rota desktop não permitida.")
    return {"command": "navigate", "route": route}


class IpcClient:
    def __init__(
        self,
        *,
        state_store: RuntimeStateStore | None = None,
        logger: logging.Logger | None = None,
        sender: Callable[..., dict[str, Any] | None] = send_request,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.state_store = state_store or RuntimeStateStore(logger=self.logger)
        self.sender = sender
        self.monotonic = monotonic
        self.sleeper = sleeper

    def deliver(
        self,
        *,
        route: str | None = None,
        timeout: float = 6.0,
        interval: float = 0.25,
    ) -> bool:
        request = command_request(route)
        deadline = self.monotonic() + timeout
        while self.monotonic() < deadline:
            info = self.state_store.load()
            if info is None:
                self.sleeper(interval)
                continue
            if not self.state_store.is_process_alive(info):
                self.state_store.clear(
                    expected_pid=info.pid,
                    expected_port=info.control_port,
                )
                self.sleeper(interval)
                continue
            if os.name == "nt":
                try:
                    ctypes.windll.user32.AllowSetForegroundWindow(info.pid)
                except OSError:
                    pass
            ping = self.sender(info, {"command": "ping"})
            if ping and ping.get("success"):
                response = self.sender(info, request)
                if response and response.get("success"):
                    self.logger.info(
                        "Comando entregue à instância existente: %s.",
                        response.get("action"),
                    )
                    return True
            self.sleeper(interval)
        return False
