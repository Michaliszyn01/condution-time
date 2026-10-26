from __future__ import annotations

import argparse
import ctypes
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Sequence

from desktop import APP_NAME
from desktop.app_state import DesktopAppState
from desktop.bridge import DesktopBridge
from desktop.config import DesktopSettingsStore
from desktop.bridge import ALLOWED_ROUTES
from desktop.ipc_client import IpcClient
from desktop.ipc_server import IpcServer
from desktop.paths import ensure_app_directories, get_log_path
from desktop.runtime_state import RuntimeStateStore
from desktop.server_manager import ServerManager
from desktop.single_instance import SingleInstance, show_already_running_message
from desktop.tray import TrayController
from desktop.monitoring import ComputerMonitorAgent
from app.health_import import HealthImportWatcher


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a porta deve ser um número") from None
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("a porta deve estar entre 1024 e 65535")
    return port


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aplicativo desktop Condution Time")
    parser.add_argument(
        "--background",
        action="store_true",
        help="inicia minimizado na bandeja",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="force_open",
        help="força a abertura da janela principal",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="executa sem ícone na bandeja",
    )
    parser.add_argument(
        "--port",
        type=valid_port,
        help="define a porta local preferida para esta execução",
    )
    parser.add_argument(
        "--route",
        choices=sorted(ALLOWED_ROUTES),
        help="abre uma rota interna permitida na janela principal",
    )
    return parser.parse_args(argv)


def configure_logging() -> logging.Logger:
    ensure_app_directories()
    logger = logging.getLogger("condution_time.desktop")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            get_log_path(),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        if not getattr(sys, "frozen", False):
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            logger.addHandler(console)
    return logger


def show_startup_error(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            APP_NAME,
            0x00000010,
        )
    except OSError:
        pass


def should_hide_window(args: argparse.Namespace, settings: Any, use_tray: bool) -> bool:
    if args.force_open or args.route or not use_tray:
        return False
    return bool(
        args.background
        or settings.start_minimized
        or not settings.open_at_startup
    )


def run_desktop(
    args: argparse.Namespace,
    *,
    webview_module: Any | None = None,
    instance: SingleInstance | None = None,
) -> int:
    logger = configure_logging()
    single_instance = instance or SingleInstance()
    runtime_store = RuntimeStateStore(logger=logger)
    if not single_instance.acquire():
        delivered = IpcClient(
            state_store=runtime_store,
            logger=logger,
        ).deliver(route=args.route)
        if delivered:
            return 0
        show_already_running_message(
            "Condution Time já está em execução, mas não foi possível "
            "restaurar a janela."
        )
        return 2
    runtime_store.clear()
    logger.info("Aplicativo desktop iniciado.")

    state = DesktopAppState()
    settings_store = DesktopSettingsStore(logger=logger)
    settings = settings_store.load()
    server = ServerManager(state, logger=logger)
    tray: TrayController | None = None
    ipc: IpcServer | None = None
    monitor: ComputerMonitorAgent | None = None
    health_watcher: HealthImportWatcher | None = None
    bridge: DesktopBridge

    def shutdown(*, destroy_window: bool = True) -> None:
        if not state.begin_shutdown():
            return
        logger.info("Encerramento solicitado.")
        if monitor is not None:
            monitor.stop()
        if health_watcher is not None:
            health_watcher.stop()
        if ipc is not None:
            ipc.stop()
        if tray is not None:
            tray.stop()
        if destroy_window and state.window is not None:
            try:
                state.window.destroy()
            except Exception:
                logger.debug("A janela já estava encerrada.", exc_info=True)
        server.stop()
        single_instance.release()

    bridge = DesktopBridge(
        state,
        settings_store,
        logger=logger,
        shutdown_callback=shutdown,
    )

    try:
        ipc = IpcServer(
            lambda action, route: bridge.show_main_window(
                route if action == "navigate" else None
            ),
            state_store=runtime_store,
            logger=logger,
        )
        ipc.start()
        base_url = server.start(
            preferred_port=settings.preferred_port,
            desktop_bridge=bridge,
            port_override=args.port,
        )
        monitor = ComputerMonitorAgent(
            server.app,
            sample_interval_seconds=settings.sample_interval_seconds,
            idle_threshold_seconds=settings.idle_threshold_seconds,
            logger=logger,
        )
        server.app.config["COMPUTER_MONITOR_AGENT"] = monitor
        if settings.monitoring_enabled and settings.start_monitoring_with_app:
            monitor.start()
        health_watcher = HealthImportWatcher(
            server.app,
            settings_store,
            logger=logger,
        )
        server.app.config["HEALTH_IMPORT_WATCHER"] = health_watcher
        if settings.health_import_enabled:
            health_watcher.start()
        use_tray = not args.no_tray
        if use_tray:
            tray = TrayController(
                state,
                bridge,
                logger=logger,
                monitor_agent=monitor,
                health_watcher=health_watcher,
            )
            tray.start()

        hidden = should_hide_window(args, settings, use_tray)

        webview = webview_module
        if webview is None:
            import webview as imported_webview

            webview = imported_webview

        window = webview.create_window(
            APP_NAME,
            f"{base_url}{args.route or ''}",
            width=settings.window_width,
            height=settings.window_height,
            min_size=(1100, 700),
            resizable=True,
            hidden=hidden,
            confirm_close=False,
        )
        bridge.set_window(window)
        window.events.loaded += bridge.mark_window_ready

        def on_closing() -> bool:
            current = settings_store.load()
            if use_tray and current.continue_in_tray and not state.shutting_down:
                window.hide()
                logger.info("Janela ocultada; aplicativo permanece na bandeja.")
                return False
            shutdown(destroy_window=False)
            return True

        window.events.closing += on_closing
        signal.signal(signal.SIGINT, lambda *_args: shutdown())
        signal.signal(signal.SIGTERM, lambda *_args: shutdown())
        logger.info("Janela desktop preparada na porta %s.", state.port)
        webview.start()
        shutdown(destroy_window=False)
        return 0
    except Exception as exc:
        logger.exception("Falha ao iniciar o aplicativo desktop.")
        show_startup_error(
            "Não foi possível iniciar o Condution Time.\n\n"
            f"{exc}\n\nConsulte a pasta de logs para obter detalhes."
        )
        shutdown()
        return 1
    finally:
        if monitor is not None:
            monitor.stop()
        if health_watcher is not None:
            health_watcher.stop()
        if ipc is not None:
            ipc.stop()
        single_instance.release()


def main(argv: Sequence[str] | None = None) -> int:
    return run_desktop(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
