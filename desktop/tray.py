from __future__ import annotations

import logging
from typing import Any

from desktop.app_state import DesktopAppState
from desktop.bridge import DesktopBridge
from desktop.paths import get_icon_path
from desktop.startup_manager import is_startup_enabled


class TrayController:
    def __init__(
        self,
        state: DesktopAppState,
        bridge: DesktopBridge,
        *,
        logger: logging.Logger | None = None,
        monitor_agent: Any | None = None,
        health_watcher: Any | None = None,
    ) -> None:
        self.state = state
        self.bridge = bridge
        self.logger = logger or logging.getLogger(__name__)
        self.monitor_agent = monitor_agent
        self.health_watcher = health_watcher
        self.icon: Any = None

    @staticmethod
    def _image() -> Any:
        from PIL import Image, ImageDraw

        icon_path = get_icon_path()
        if icon_path:
            return Image.open(icon_path)
        image = Image.new("RGBA", (64, 64), (36, 107, 253, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((3, 3, 61, 61), radius=16, fill=(36, 107, 253, 255))
        draw.ellipse((18, 18, 46, 46), outline="white", width=5)
        draw.line((32, 11, 32, 22), fill="white", width=5)
        draw.line((32, 42, 32, 53), fill="white", width=5)
        return image

    def _toggle_startup(self, _icon: Any, _item: Any) -> None:
        current = is_startup_enabled()
        self.bridge.update_settings({"start_with_windows": not current})
        if self.icon:
            self.icon.update_menu()

    def _monitor_status_label(self, _item: Any = None) -> str:
        if self.monitor_agent is None:
            return "Status: monitor indisponível"
        status = self.monitor_agent.status()["status"]
        return {
            "running": "Status: monitorando",
            "paused": "Status: pausado",
            "stopped": "Status: desligado",
            "error": "Status: erro",
        }.get(status, "Status: desligado")

    def _monitor_action_label(self, _item: Any = None) -> str:
        if self.monitor_agent is None:
            return "Iniciar monitoramento"
        return {
            "running": "Pausar monitoramento",
            "paused": "Retomar monitoramento",
            "stopped": "Iniciar monitoramento",
            "error": "Tentar novamente",
        }.get(self.monitor_agent.status()["status"], "Iniciar monitoramento")

    def _toggle_monitor(self, _icon: Any, _item: Any) -> None:
        if self.monitor_agent is None:
            return
        status = self.monitor_agent.status()["status"]
        if status == "running":
            self.monitor_agent.pause()
        elif status == "paused":
            self.monitor_agent.resume()
        else:
            self.monitor_agent.start()
        if self.icon:
            self.icon.update_menu()

    def _health_status_label(self, _item: Any = None) -> str:
        if self.health_watcher is None:
            return "Saúde: indisponível"
        status = self.health_watcher.status()["status"]
        return {
            "connected": "Saúde: conectado",
            "importing": "Saúde: importando",
            "waiting_for_file": "Saúde: aguardando arquivo",
            "error": "Saúde: erro",
            "disabled": "Saúde: desativado",
        }.get(status, "Saúde: aguardando arquivo")

    def _import_health(self, _icon: Any, _item: Any) -> None:
        if self.health_watcher is None:
            return
        try:
            self.health_watcher.import_now()
        except Exception:
            self.logger.exception("Falha na importação manual pela bandeja.")
        if self.icon:
            self.icon.update_menu()

    def start(self) -> None:
        import pystray

        if self.icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem(
                "Abrir Condution Time",
                lambda _icon, _item: self.bridge.show_main_window("/"),
                default=True,
            ),
            pystray.MenuItem(
                "Registrar atividade",
                lambda _icon, _item: self.bridge.show_main_window("/registrar"),
            ),
            pystray.MenuItem(
                "Iniciar sessão",
                lambda _icon, _item: self.bridge.show_main_window("/sessao"),
            ),
            pystray.MenuItem(
                "Abrir Histórico",
                lambda _icon, _item: self.bridge.show_main_window("/historico"),
            ),
            pystray.MenuItem(
                "Abrir Uso do computador",
                lambda _icon, _item: self.bridge.show_main_window("/computador"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Iniciar com o Windows",
                self._toggle_startup,
                checked=lambda _item: is_startup_enabled(),
            ),
            pystray.MenuItem("Servidor: ativo", None, enabled=False),
            pystray.MenuItem(self._monitor_status_label, None, enabled=False),
            pystray.MenuItem(
                self._monitor_action_label,
                self._toggle_monitor,
                enabled=self.monitor_agent is not None,
            ),
            pystray.MenuItem(self._health_status_label, None, enabled=False),
            pystray.MenuItem(
                "Importar saúde agora",
                self._import_health,
                enabled=self.health_watcher is not None,
            ),
            pystray.MenuItem(
                "Abrir Conexão com Saúde",
                lambda _icon, _item: self.bridge.show_main_window(
                    "/configuracoes"
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Sair",
                lambda _icon, _item: self.bridge.request_exit(),
            ),
        )
        self.icon = pystray.Icon(
            "CondutionTime",
            self._image(),
            "Condution Time",
            menu,
        )
        self.icon.run_detached()
        self.state.tray_active = True
        self.logger.info("Ícone de bandeja iniciado.")

    def stop(self) -> None:
        if self.icon is None:
            return
        try:
            self.icon.stop()
        finally:
            self.icon = None
            self.state.tray_active = False
            self.logger.info("Ícone de bandeja encerrado.")
