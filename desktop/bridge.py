from __future__ import annotations

import logging
import os
import ctypes
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from desktop.app_state import DesktopAppState
from desktop.config import DesktopSettings, DesktopSettingsStore
from desktop.paths import get_data_dir, get_logs_dir
from desktop.startup_manager import is_startup_enabled, set_startup_enabled


ALLOWED_ROUTES = {
    "/",
    "/registrar",
    "/sessao",
    "/historico",
    "/configuracoes",
    "/computador",
    "/perfil",
}
ALLOWED_SETTING_KEYS = {
    "start_with_windows",
    "start_minimized",
    "open_at_startup",
    "continue_in_tray",
    "preferred_port",
    "window_width",
    "window_height",
    "monitoring_enabled",
    "start_monitoring_with_app",
    "idle_threshold_seconds",
    "sample_interval_seconds",
    "health_import_enabled",
    "health_import_poll_seconds",
    "health_import_stability_seconds",
}


class DesktopBridge:
    def __init__(
        self,
        state: DesktopAppState,
        settings_store: DesktopSettingsStore,
        *,
        logger: logging.Logger | None = None,
        shutdown_callback: Callable[[], None] | None = None,
        folder_opener: Callable[[str], Any] | None = None,
        startup_setter: Callable[[bool], bool] = set_startup_enabled,
        startup_checker: Callable[[], bool] = is_startup_enabled,
        window_focuser: Callable[[Any], bool] | None = None,
        folder_selector: Callable[[], str | None] | None = None,
    ) -> None:
        self.state = state
        self.settings_store = settings_store
        self.logger = logger or logging.getLogger(__name__)
        self.shutdown_callback = shutdown_callback
        self.folder_opener = folder_opener or self._default_folder_opener
        self.startup_setter = startup_setter
        self.startup_checker = startup_checker
        self.window_focuser = window_focuser or self._focus_native_window
        self.folder_selector = folder_selector or self._default_folder_selector

    @staticmethod
    def _default_folder_opener(path: str) -> None:
        if os.name != "nt":
            raise OSError("Abertura de pasta disponível apenas no Windows.")
        os.startfile(path)

    def set_window(self, window: Any) -> None:
        self.state.window = window

    @staticmethod
    def _focus_native_window(window: Any) -> bool:
        if os.name != "nt":
            return False
        native = getattr(window, "native", None)
        handle = getattr(native, "Handle", None)
        if handle is None:
            return False
        try:
            converter = getattr(handle, "ToInt64", None) or getattr(
                handle, "ToInt32", None
            )
            hwnd = int(converter() if callable(converter) else handle)
            if not hwnd:
                return False
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def mark_window_ready(self) -> None:
        requested, route = self.state.mark_window_ready()
        if requested:
            self.show_main_window(route)

    def get_settings(self) -> dict[str, Any]:
        settings = self.settings_store.load()
        payload = asdict(settings)
        payload["start_with_windows"] = self.startup_checker()
        payload.update(self.state.snapshot())
        return payload

    def update_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(changes, dict):
            raise ValueError("Envie um objeto de configurações válido.")
        unknown = sorted(set(changes) - ALLOWED_SETTING_KEYS)
        if unknown:
            raise ValueError(f"Configurações não permitidas: {', '.join(unknown)}.")
        if "preferred_port" in changes:
            try:
                port = int(changes["preferred_port"])
            except (TypeError, ValueError):
                raise ValueError("Informe uma porta válida.") from None
            if port < 5000 or port > 5010:
                raise ValueError("A porta preferida deve estar entre 5000 e 5010.")
            changes["preferred_port"] = port
        if "start_with_windows" in changes:
            enabled = self.startup_setter(bool(changes["start_with_windows"]))
            changes["start_with_windows"] = enabled
        if "idle_threshold_seconds" in changes:
            try:
                idle_threshold = int(changes["idle_threshold_seconds"])
            except (TypeError, ValueError):
                raise ValueError("Informe um limite de ociosidade válido.") from None
            if not 60 <= idle_threshold <= 7200:
                raise ValueError(
                    "O limite de ociosidade deve ficar entre 60 e 7200 segundos."
                )
            changes["idle_threshold_seconds"] = idle_threshold
        if "sample_interval_seconds" in changes:
            try:
                sample_interval = int(changes["sample_interval_seconds"])
            except (TypeError, ValueError):
                raise ValueError("Informe um intervalo de captura válido.") from None
            if not 1 <= sample_interval <= 10:
                raise ValueError(
                    "O intervalo de captura deve ficar entre 1 e 10 segundos."
                )
            changes["sample_interval_seconds"] = sample_interval
        for key, minimum, maximum, label in (
            ("health_import_poll_seconds", 30, 3600, "intervalo de busca"),
            ("health_import_stability_seconds", 5, 120, "tempo de estabilidade"),
        ):
            if key not in changes:
                continue
            try:
                value = int(changes[key])
            except (TypeError, ValueError):
                raise ValueError(f"Informe um {label} válido.") from None
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"O {label} deve ficar entre {minimum} e {maximum} segundos."
                )
            changes[key] = value
        saved = self.settings_store.update(changes)
        return {**asdict(saved), **self.state.snapshot()}

    def show_main_window(self, route: str | None = None) -> bool:
        if route is not None and route not in ALLOWED_ROUTES:
            raise ValueError("Rota desktop não permitida.")
        window = self.state.window
        if self.state.shutting_down:
            return False
        if window is None or not self.state.window_ready:
            self.state.request_window(route)
            return True
        if route is not None:
            base_url = self.state.base_url
            loader = getattr(window, "load_url", None)
            if base_url is None or not callable(loader):
                return False
            loader(f"{base_url}{route}")
        for method_name in ("show", "restore", "bring_to_front"):
            method = getattr(window, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    self.logger.debug(
                        "Método de janela indisponível: %s",
                        method_name,
                        exc_info=True,
                    )
        self.window_focuser(window)
        return True

    def show_window(self) -> bool:
        return self.show_main_window()

    def navigate(self, route: str) -> bool:
        return self.show_main_window(route)

    def _open_known_folder(self, path: Path) -> bool:
        path.mkdir(parents=True, exist_ok=True)
        self.folder_opener(str(path.resolve()))
        return True

    def open_data_folder(self) -> bool:
        return self._open_known_folder(get_data_dir())

    def open_logs_folder(self) -> bool:
        return self._open_known_folder(get_logs_dir())

    @staticmethod
    def _default_folder_selector() -> str | None:
        if os.name != "nt":
            return None
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(
                title="Selecione a pasta sincronizada com a saúde"
            )
            return selected or None
        finally:
            root.destroy()

    def select_health_import_folder(self) -> str | None:
        selected = self.folder_selector()
        if not selected:
            return None
        folder = Path(selected).resolve(strict=True)
        if not folder.is_dir():
            raise ValueError("A pasta selecionada não é válida.")
        self.settings_store.update({"health_import_folder": str(folder)})
        return str(folder)

    def request_exit(self) -> None:
        if self.shutdown_callback:
            self.shutdown_callback()
