from __future__ import annotations

import json
import logging
import socket
import threading
from collections.abc import Callable
from typing import Any

from desktop.bridge import ALLOWED_ROUTES
from desktop.runtime_state import RuntimeInfo, RuntimeStateStore


CONTROL_HOST = "127.0.0.1"
MAX_MESSAGE_BYTES = 2048


class IpcServer:
    def __init__(
        self,
        action_callback: Callable[[str, str | None], bool],
        *,
        state_store: RuntimeStateStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.action_callback = action_callback
        self.logger = logger or logging.getLogger(__name__)
        self.state_store = state_store or RuntimeStateStore(logger=self.logger)
        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.runtime_info: RuntimeInfo | None = None
        self.stopping = threading.Event()

    def start(self) -> RuntimeInfo:
        if self.socket is not None:
            raise RuntimeError("O servidor IPC já foi iniciado.")
        control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        control_socket.bind((CONTROL_HOST, 0))
        control_socket.listen(5)
        control_socket.settimeout(0.25)
        port = int(control_socket.getsockname()[1])
        info = RuntimeInfo.create(port)
        self.state_store.save(info)
        self.socket = control_socket
        self.runtime_info = info
        self.stopping.clear()
        self.thread = threading.Thread(
            target=self._serve,
            name="CondutionTimeIPC",
            daemon=True,
        )
        self.thread.start()
        self.logger.info("Canal IPC local iniciado na porta %s.", port)
        return info

    def _serve(self) -> None:
        while not self.stopping.is_set():
            try:
                connection, _address = self.socket.accept() if self.socket else (None, None)
            except socket.timeout:
                continue
            except OSError:
                break
            if connection is None:
                continue
            with connection:
                connection.settimeout(1.0)
                response = self._handle_connection(connection)
                try:
                    connection.sendall(
                        json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
                    )
                except OSError:
                    self.logger.debug("Cliente IPC desconectou antes da resposta.")

    def _handle_connection(self, connection: socket.socket) -> dict[str, Any]:
        try:
            payload = connection.recv(MAX_MESSAGE_BYTES + 1)
            if len(payload) > MAX_MESSAGE_BYTES:
                raise ValueError("Mensagem IPC excede o limite.")
            request = json.loads(payload.decode("utf-8").strip())
            if not isinstance(request, dict):
                raise ValueError("Mensagem IPC inválida.")
            command = request.get("command")
            if command == "ping":
                return {"success": True, "action": "ping"}
            if command == "show_window":
                success = bool(self.action_callback("show_window", None))
                return {"success": success, "action": "show_window"}
            if command == "navigate":
                route = request.get("route")
                if route not in ALLOWED_ROUTES:
                    raise ValueError("Rota IPC não permitida.")
                success = bool(self.action_callback("navigate", route))
                return {"success": success, "action": f"navigate:{route}"}
            raise ValueError("Comando IPC não permitido.")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return {"success": False, "error": str(exc)}
        except Exception:
            self.logger.exception("Falha ao executar ação IPC.")
            return {"success": False, "error": "Falha ao executar ação."}

    def stop(self) -> None:
        if (
            self.socket is None
            and self.thread is None
            and self.runtime_info is None
        ):
            return
        info = self.runtime_info
        self.stopping.set()
        control_socket = self.socket
        self.socket = None
        if control_socket is not None:
            try:
                control_socket.close()
            except OSError:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None
        self.runtime_info = None
        if info is not None:
            self.state_store.clear(
                expected_pid=info.pid,
                expected_port=info.control_port,
            )
        self.logger.info("Canal IPC local encerrado.")
