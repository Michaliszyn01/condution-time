from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from app import create_app
from app.extensions import db
from desktop.app_state import DesktopAppState
from desktop.paths import (
    get_data_dir,
    get_database_path,
    is_frozen,
    resource_path,
    sqlite_uri,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
MAX_PORT_ATTEMPTS = 11


class ServerStartError(RuntimeError):
    pass


def is_port_available(host: str, port: int) -> bool:
    if host != DEFAULT_HOST:
        raise ValueError("O servidor desktop deve usar apenas 127.0.0.1.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(
    preferred_port: int = DEFAULT_PORT,
    *,
    host: str = DEFAULT_HOST,
    attempts: int = MAX_PORT_ATTEMPTS,
    checker: Callable[[str, int], bool] = is_port_available,
) -> int:
    if preferred_port < 1024 or preferred_port > 65535:
        raise ValueError("A porta deve estar entre 1024 e 65535.")
    for offset in range(max(1, attempts)):
        candidate = preferred_port + offset
        if candidate > 65535:
            break
        if checker(host, candidate):
            return candidate
    raise ServerStartError("Nenhuma porta local disponível na faixa configurada.")


def health_check(url: str, *, timeout: float = 1.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status == 200 and b'"ok"' in response.read(256)
    except (OSError, URLError, TimeoutError):
        return False


def wait_until_ready(
    health_url: str,
    *,
    timeout: float = 15.0,
    interval: float = 0.2,
    checker: Callable[[str], bool] = health_check,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if checker(health_url):
            return True
        time.sleep(interval)
    return False


def _default_server_factory(app: Any, host: str, port: int) -> Any:
    try:
        from waitress import create_server

        return create_server(app, host=host, port=port, threads=4)
    except ImportError:
        from werkzeug.serving import make_server

        return make_server(host, port, app, threaded=True)


class ServerManager:
    def __init__(
        self,
        state: DesktopAppState,
        *,
        logger: logging.Logger | None = None,
        app_factory: Callable[..., Any] = create_app,
        server_factory: Callable[[Any, str, int], Any] = _default_server_factory,
        ready_waiter: Callable[..., bool] = wait_until_ready,
    ) -> None:
        self.state = state
        self.logger = logger or logging.getLogger(__name__)
        self.app_factory = app_factory
        self.server_factory = server_factory
        self.ready_waiter = ready_waiter
        self.app: Any = None
        self.server: Any = None
        self.thread: threading.Thread | None = None

    def _app_config(self, desktop_bridge: Any) -> dict[str, Any]:
        config: dict[str, Any] = {
            "DESKTOP_MODE": True,
            "DESKTOP_BRIDGE": desktop_bridge,
        }
        if is_frozen():
            config["SQLALCHEMY_DATABASE_URI"] = sqlite_uri(get_database_path())
            config["INSTANCE_PATH"] = str(get_data_dir())
        return config

    def _upgrade_database(self) -> None:
        from flask_migrate import upgrade

        migrations_dir = resource_path("migrations")
        if not migrations_dir.is_dir():
            raise ServerStartError("As migrações do banco não foram encontradas.")
        with self.app.app_context():
            upgrade(directory=str(migrations_dir))

    def start(
        self,
        *,
        preferred_port: int,
        desktop_bridge: Any,
        port_override: int | None = None,
        run_migrations: bool = True,
    ) -> str:
        if self.server is not None:
            raise ServerStartError("O servidor desktop já foi iniciado.")
        port = find_available_port(port_override or preferred_port)
        self.app = self.app_factory(self._app_config(desktop_bridge))
        # Flask usa seu próprio logger. Reaproveitar os handlers rotativos do
        # desktop garante traceback completo no mesmo arquivo local.
        self.app.logger.handlers = list(self.logger.handlers)
        self.app.logger.setLevel(self.logger.level)
        self.app.logger.propagate = False
        if run_migrations:
            self._upgrade_database()
            # O alembic.ini usa logging.fileConfig, que pode desabilitar loggers
            # já existentes durante a migração.
            self.logger.disabled = False
        self.server = self.server_factory(self.app, DEFAULT_HOST, port)
        runner = getattr(self.server, "run", None) or getattr(
            self.server, "serve_forever", None
        )
        if not callable(runner):
            raise ServerStartError("O servidor WSGI não possui método de execução.")
        self.thread = threading.Thread(
            target=runner,
            name="CondutionTimeServer",
            daemon=True,
        )
        self.thread.start()
        self.state.port = port
        health_url = f"http://{DEFAULT_HOST}:{port}/health"
        if not self.ready_waiter(health_url, timeout=15.0):
            self.stop()
            raise ServerStartError(
                "O servidor local não respondeu dentro do tempo esperado."
            )
        self.state.server_active = True
        self.logger.info("Servidor local iniciado na porta %s.", port)
        return f"http://{DEFAULT_HOST}:{port}"

    def stop(self) -> None:
        server = self.server
        if server is None:
            return
        try:
            dispatcher = getattr(server, "task_dispatcher", None)
            if dispatcher and hasattr(dispatcher, "shutdown"):
                dispatcher.shutdown()
            stopper = getattr(server, "close", None) or getattr(server, "shutdown", None)
            if callable(stopper):
                stopper()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5)
            if self.app is not None:
                with self.app.app_context():
                    db.session.remove()
        finally:
            self.state.server_active = False
            self.server = None
            self.thread = None
            self.logger.info("Servidor local encerrado.")
