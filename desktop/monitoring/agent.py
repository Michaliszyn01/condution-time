from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from desktop.monitoring.aggregator import ActivityAggregator
from desktop.monitoring.classifier import ApplicationClassifier
from desktop.monitoring.constants import (
    IDLE_THRESHOLD_SECONDS,
    MONITOR_SAMPLE_INTERVAL_SECONDS,
)
from desktop.monitoring.foreground import ForegroundCapture
from desktop.monitoring.idle import get_idle_seconds
from desktop.monitoring.repository import MonitoringRepository
from desktop.monitoring.state import MonitorRuntimeState


class ComputerMonitorAgent:
    def __init__(
        self,
        app: Any,
        *,
        sample_interval_seconds: int = MONITOR_SAMPLE_INTERVAL_SECONDS,
        idle_threshold_seconds: int = IDLE_THRESHOLD_SECONDS,
        capture: Any | None = None,
        idle_reader: Callable[[], float] = get_idle_seconds,
        repository: MonitoringRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.app = app
        self.logger = logger or logging.getLogger(__name__)
        self.repository = repository or MonitoringRepository(app, logger=self.logger)
        self.capture = capture or ForegroundCapture()
        self.idle_reader = idle_reader
        self.classifier = ApplicationClassifier(self.repository)
        self.state = MonitorRuntimeState()
        self._sample_interval = self._valid_interval(sample_interval_seconds)
        self._idle_threshold = self._valid_idle_threshold(idle_threshold_seconds)
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self.aggregator = ActivityAggregator(
            self._persist_block,
            timezone_name=app.config.get("APP_TIMEZONE", "America/Sao_Paulo"),
        )

    @staticmethod
    def _valid_interval(value: Any) -> int:
        parsed = int(value)
        if not 1 <= parsed <= 10:
            raise ValueError("O intervalo deve ficar entre 1 e 10 segundos.")
        return parsed

    @staticmethod
    def _valid_idle_threshold(value: Any) -> int:
        parsed = int(value)
        if not 60 <= parsed <= 7200:
            raise ValueError("O limite de ociosidade deve ficar entre 60 e 7200 segundos.")
        return parsed

    def configure(
        self,
        *,
        sample_interval_seconds: int | None = None,
        idle_threshold_seconds: int | None = None,
    ) -> None:
        with self._lock:
            if sample_interval_seconds is not None:
                self._sample_interval = self._valid_interval(sample_interval_seconds)
            if idle_threshold_seconds is not None:
                self._idle_threshold = self._valid_idle_threshold(idle_threshold_seconds)
        self._wake_event.set()

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self.state.paused:
                    return self.resume()
                return False
            self._stop_event.clear()
            self._wake_event.clear()
            self.state.update(status="running", paused=False, recent_errors=[])
            self._thread = threading.Thread(
                target=self._run,
                name="CondutionTimeComputerMonitor",
                daemon=True,
            )
            self._thread.start()
        self.logger.info("Monitor do computador iniciado.")
        return True

    def pause(self) -> bool:
        with self._lock:
            if self.state.status != "running":
                return False
            self.state.update(
                status="paused",
                paused=True,
                current_process=None,
                current_project=None,
                current_site=None,
            )
            self.aggregator.pause(datetime.now(timezone.utc))
            self._wake_event.set()
        self.logger.info("Monitor do computador pausado.")
        return True

    def resume(self) -> bool:
        with self._lock:
            if self.state.status != "paused":
                return False
            self.state.update(status="running", paused=False, recent_errors=[])
            self._wake_event.set()
        self.logger.info("Monitor do computador retomado.")
        return True

    def stop(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                self.state.update(status="stopped", paused=False)
                return False
            self._stop_event.set()
            self._wake_event.set()
        if thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=5)
        self.aggregator.stop(datetime.now(timezone.utc))
        with self._lock:
            self._thread = None
            self.state.update(
                status="stopped",
                paused=False,
                current_process=None,
                current_project=None,
                current_site=None,
                current_block_started_at=None,
            )
        self.logger.info("Monitor do computador encerrado.")
        return True

    def status(self) -> dict[str, Any]:
        payload = self.state.snapshot()
        payload.update(
            sample_interval_seconds=self._sample_interval,
            idle_threshold_seconds=self._idle_threshold,
        )
        return payload

    def _persist_block(self, block: Any) -> None:
        persisted = self.repository.save_block(block)
        if persisted is not None:
            self.state.update(
                blocks_persisted=self.state.blocks_persisted + 1,
            )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self.state.paused:
                self._sample_once()
            with self._lock:
                interval = self._sample_interval
            self._wake_event.wait(interval)
            self._wake_event.clear()

    def _sample_once(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            idle_seconds = float(self.idle_reader())
            local_date = now.astimezone(self.aggregator.timezone).date()
            session = self.repository.get_active_session(local_date)
            app = None if idle_seconds >= self._idle_threshold else self.capture.capture()
            transient_title = None
            if app is not None:
                title_reader = getattr(self.capture, "capture_context_title", None)
                if callable(title_reader):
                    transient_title = title_reader(app)
            classification = (
                self.classifier.classify(
                    app.executable_name,
                    session,
                    transient_title=transient_title,
                )
                if app is not None
                else None
            )
            transient_title = None
            self.aggregator.observe(
                now,
                app,
                classification,
                session,
                idle_seconds=idle_seconds,
                idle_threshold_seconds=self._idle_threshold,
            )
            self.state.update(
                status="running",
                current_process=app.executable_name if app else None,
                current_project=(
                    classification.project_display_name if classification else None
                ),
                current_site=classification.site_key if classification else None,
                current_block_started_at=(
                    self.aggregator.current.started_at
                    if self.aggregator.current
                    else None
                ),
                last_capture_at=now,
                idle_seconds=idle_seconds,
            )
        except Exception as exc:
            self.aggregator.invalidate(now)
            self.state.add_error(type(exc).__name__)
            self.logger.warning(
                "Erro ao consultar processo em primeiro plano: %s",
                type(exc).__name__,
            )
