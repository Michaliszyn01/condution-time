from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.health_import.constants import SOURCE_PROVIDER
from app.models import (
    BodyMeasurement,
    DailyHealthSummary,
    SleepRecord,
    TrainingRecord,
)


class ImportStats:
    def __init__(self) -> None:
        self.imported = 0
        self.updated = 0
        self.skipped = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "imported": self.imported,
            "updated": self.updated,
            "skipped": self.skipped,
        }


class HealthImportRepository:
    def __init__(self) -> None:
        self.stats = ImportStats()

    @staticmethod
    def _apply(model: Any, payload: dict) -> None:
        for key, value in payload.items():
            setattr(model, key, value)

    def upsert_sleep(self, payload: dict) -> None:
        existing = db.session.scalar(
            db.select(SleepRecord).where(
                SleepRecord.source_record_id == payload["source_record_id"]
            )
        )
        local_date = payload["record_date"]
        if existing is None and payload.get("is_primary", True):
            existing = db.session.scalar(
                db.select(SleepRecord).where(
                    SleepRecord.record_date == local_date,
                    SleepRecord.is_primary.is_(True),
                    SleepRecord.source_record_id.is_(None),
                )
            )
        if existing and existing.source_hash == payload["source_hash"]:
            self.stats.skipped += 1
            return
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = SleepRecord(
                record_date=local_date,
                sleep_start=payload["sleep_started_at"].astimezone().time().replace(
                    tzinfo=None
                ),
                sleep_end=payload["sleep_ended_at"].astimezone().time().replace(
                    tzinfo=None
                ),
                perceived_quality=None,
                woke_restored=None,
                notes=None,
                record_origin="health_connect",
                source_provider=SOURCE_PROVIDER,
                imported_at=now,
                suggestion_status="available",
            )
            db.session.add(existing)
            self.stats.imported += 1
        else:
            if existing.record_origin == "manual":
                existing.record_origin = "merged"
            self.stats.updated += 1
        self._apply(existing, payload)
        existing.source_provider = SOURCE_PROVIDER
        existing.imported_at = existing.imported_at or now
        existing.sleep_start = payload["sleep_started_at"].astimezone().time().replace(
            tzinfo=None
        )
        existing.sleep_end = payload["sleep_ended_at"].astimezone().time().replace(
            tzinfo=None
        )

    def upsert_training(self, payload: dict) -> None:
        existing = db.session.scalar(
            db.select(TrainingRecord).where(
                TrainingRecord.source_record_id == payload["source_record_id"]
            )
        )
        if existing and existing.source_hash == payload["source_hash"]:
            self.stats.skipped += 1
            return
        now = datetime.now(timezone.utc)
        if existing is None:
            start = payload["training_started_at"]
            candidates = db.session.scalars(
                db.select(TrainingRecord).where(
                    TrainingRecord.record_date == payload["record_date"],
                    TrainingRecord.source_record_id.is_(None),
                )
            )
            existing = next(
                (
                    item
                    for item in candidates
                    if item.training_started_at
                    and abs((item.training_started_at - start).total_seconds()) <= 600
                ),
                None,
            )
        if existing is None:
            existing = TrainingRecord(
                record_date=payload["record_date"],
                training_type=payload["training_type"],
                activity_name=payload["activity_name"],
                duration_minutes=payload["duration_minutes"],
                intensity=None,
                perceived_performance=None,
                discomfort_level=None,
                record_origin="health_connect",
                source_provider=SOURCE_PROVIDER,
                imported_at=now,
                suggestion_status="available",
            )
            db.session.add(existing)
            self.stats.imported += 1
        else:
            if existing.record_origin == "manual":
                existing.record_origin = "merged"
            self.stats.updated += 1
        subjective = {
            key: getattr(existing, key)
            for key in (
                "intensity",
                "perceived_performance",
                "exercises_text",
                "discomfort_level",
                "discomfort_location",
                "notes",
                "manual_training_type",
            )
        }
        preserve_manual_classification = (
            existing.record_origin == "merged"
            and existing.manual_training_type is not None
        )
        manual_activity_name = existing.activity_name
        self._apply(existing, payload)
        for key, value in subjective.items():
            setattr(existing, key, value)
        if preserve_manual_classification:
            existing.activity_name = manual_activity_name
        existing.source_provider = SOURCE_PROVIDER
        existing.imported_at = existing.imported_at or now
        if any(value is not None for value in subjective.values()):
            existing.suggestion_status = "completed"

    def upsert_body(self, payload: dict) -> None:
        existing = db.session.scalar(
            db.select(BodyMeasurement).where(
                BodyMeasurement.source_provider == SOURCE_PROVIDER,
                BodyMeasurement.source_record_id == payload["source_record_id"],
            )
        )
        if existing and existing.source_hash == payload["source_hash"]:
            self.stats.skipped += 1
            return
        if existing is None:
            existing = BodyMeasurement(
                source_provider=SOURCE_PROVIDER,
                origin="health_connect",
                imported_at=datetime.now(timezone.utc),
                **payload,
            )
            db.session.add(existing)
            self.stats.imported += 1
        else:
            self._apply(existing, payload)
            self.stats.updated += 1

    def upsert_daily(self, record_date, payload: dict) -> None:
        source_hash = payload.pop("source_hash")
        existing = db.session.get(DailyHealthSummary, record_date)
        if existing and existing.source_hash == source_hash:
            self.stats.skipped += 1
            return
        if existing is None:
            existing = DailyHealthSummary(
                record_date=record_date,
                source_provider=SOURCE_PROVIDER,
                source_hash=source_hash,
            )
            db.session.add(existing)
            self.stats.imported += 1
        else:
            existing.source_hash = source_hash
            self.stats.updated += 1
        self._apply(existing, payload)
