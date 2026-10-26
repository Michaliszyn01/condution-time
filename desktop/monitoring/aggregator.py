from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from desktop.monitoring.constants import MAX_SAMPLE_GAP_SECONDS, MIN_BLOCK_SECONDS
from desktop.monitoring.state import (
    BlockDraft,
    Classification,
    ForegroundApplication,
    SessionContext,
)


class ActivityAggregator:
    """Agrupa amostras; blocos de aplicativo abaixo de 3s são ruído e descartados."""

    def __init__(
        self,
        persist: Callable[[BlockDraft], object],
        *,
        timezone_name: str = "America/Sao_Paulo",
        min_block_seconds: int = MIN_BLOCK_SECONDS,
        max_gap_seconds: int = MAX_SAMPLE_GAP_SECONDS,
    ) -> None:
        self.persist = persist
        self.timezone = ZoneInfo(timezone_name)
        self.min_block_seconds = min_block_seconds
        self.max_gap_seconds = max_gap_seconds
        self.current: BlockDraft | None = None
        self.last_sample_at: datetime | None = None

    def observe(
        self,
        captured_at: datetime,
        app: ForegroundApplication | None,
        classification: Classification | None,
        session: SessionContext | None,
        *,
        idle_seconds: float = 0,
        idle_threshold_seconds: int = 300,
    ) -> None:
        self._handle_gap(captured_at)
        local_date = captured_at.astimezone(self.timezone).date()
        if self.current and self.current.record_date != local_date:
            self._split_at_midnight(captured_at)

        is_idle = idle_seconds >= idle_threshold_seconds
        if is_idle:
            idle_start = captured_at - timedelta(
                seconds=max(0, idle_seconds - idle_threshold_seconds)
            )
            if self.current and not self.current.was_idle:
                self._close(max(self.current.started_at, idle_start))
            draft = BlockDraft(
                record_date=local_date,
                executable_name=None,
                friendly_name=None,
                classification="neutral",
                category="system",
                classification_source="fallback",
                started_at=max(idle_start, self._local_day_start(captured_at)),
                was_idle=True,
            )
        elif app is not None and classification is not None:
            draft = BlockDraft(
                record_date=local_date,
                executable_name=app.executable_name,
                friendly_name=app.friendly_name,
                classification=classification.classification,
                category=classification.category,
                classification_source=classification.source,
                started_at=captured_at,
                session_id=session.id if session else None,
                project_rule_id=classification.project_rule_id,
                project_key=classification.project_key,
                project_display_name=classification.project_display_name,
                site_key=classification.site_key,
                context_source=classification.context_source,
            )
        else:
            self.invalidate(captured_at)
            return

        if self.current is None:
            self.current = draft
        elif self.current.key() != draft.key():
            self._close(captured_at)
            self.current = draft
        self.last_sample_at = captured_at

    def pause(self, captured_at: datetime) -> None:
        self._close(captured_at)
        self.last_sample_at = None

    def stop(self, captured_at: datetime) -> None:
        self._close(captured_at)
        self.last_sample_at = None

    def invalidate(self, captured_at: datetime) -> None:
        end = self.last_sample_at or captured_at
        self._close(end)
        self.last_sample_at = captured_at

    def _handle_gap(self, captured_at: datetime) -> None:
        if self.last_sample_at is None:
            return
        gap = (captured_at - self.last_sample_at).total_seconds()
        if gap > self.max_gap_seconds:
            self._close(self.last_sample_at)
            self.last_sample_at = None

    def _split_at_midnight(self, captured_at: datetime) -> None:
        if self.current is None:
            return
        local = captured_at.astimezone(self.timezone)
        midnight = datetime.combine(local.date(), time.min, self.timezone)
        prior = self.current
        self._close(midnight)
        self.current = BlockDraft(
            record_date=local.date(),
            executable_name=prior.executable_name,
            friendly_name=prior.friendly_name,
            classification=prior.classification,
            category=prior.category,
            classification_source=prior.classification_source,
            started_at=midnight,
            was_idle=prior.was_idle,
            session_id=prior.session_id,
            project_rule_id=prior.project_rule_id,
            project_key=prior.project_key,
            project_display_name=prior.project_display_name,
            site_key=prior.site_key,
            context_source=prior.context_source,
        )

    def _local_day_start(self, captured_at: datetime) -> datetime:
        local = captured_at.astimezone(self.timezone)
        return datetime.combine(local.date(), time.min, self.timezone)

    def _close(self, ended_at: datetime) -> None:
        block = self.current
        self.current = None
        if block is None or ended_at <= block.started_at:
            return
        block.ended_at = ended_at
        duration = (ended_at - block.started_at).total_seconds()
        if block.was_idle or duration >= self.min_block_seconds:
            self.persist(block)
