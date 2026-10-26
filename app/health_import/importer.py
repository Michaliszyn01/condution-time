from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.extensions import db
from app.health_import.archive import prepare_database
from app.health_import.deduplication import normalized_hash
from app.health_import.health_connect_reader import (
    HealthConnectReader,
    open_health_database,
)
from app.health_import.mapper import map_body, map_sleep, map_training
from app.health_import.repository import HealthImportRepository
from app.models import HealthImportRun, SleepRecord, UserProfile
from app.services.notification_service import create_notification


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class HealthImporter:
    def __init__(self, app: Any) -> None:
        self.app = app

    def import_file(self, source: str | Path) -> dict:
        source_path = Path(source).resolve(strict=True)
        source_hash = hash_file(source_path)
        with self.app.app_context():
            duplicate = db.session.scalar(
                db.select(HealthImportRun).where(
                    HealthImportRun.source_hash == source_hash,
                    HealthImportRun.status.in_(
                        ("completed", "completed_with_warnings")
                    ),
                )
            )
            if duplicate:
                return {
                    "run_id": duplicate.id,
                    "status": "unchanged",
                    "imported": 0,
                    "updated": 0,
                    "skipped": duplicate.skipped_count,
                }
            run = HealthImportRun(
                source_filename=source_path.name,
                source_hash=source_hash,
                source_modified_at=datetime.fromtimestamp(
                    source_path.stat().st_mtime,
                    tz=timezone.utc,
                ),
                status="running",
            )
            db.session.add(run)
            db.session.commit()
            run_id = run.id

        work_parent = Path(self.app.instance_path) / "health-import-work"
        work_parent.mkdir(parents=True, exist_ok=True)
        work_dir = work_parent / f"run-{run_id}"
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            database_path = prepare_database(source_path, work_dir)
            repository = HealthImportRepository()
            with open_health_database(database_path) as (connection, schema):
                reader = HealthConnectReader(
                    connection,
                    schema,
                    timezone_name=self.app.config.get(
                        "APP_TIMEZONE", "America/Sao_Paulo"
                    ),
                )
                with self.app.app_context():
                    profile = db.session.scalar(db.select(UserProfile).limit(1))
                    height = profile.height_cm if profile else None
                    sleeps_by_date = {}
                    for row in reader.sleep_rows():
                        mapped = map_sleep(row, reader)
                        record_date = mapped["record_date"]
                        sleeps_by_date.setdefault(record_date, []).append(mapped)
                    for sessions in sleeps_by_date.values():
                        primary = max(
                            sessions,
                            key=lambda item: item["duration_minutes"],
                        )
                        for mapped in sessions:
                            mapped["is_primary"] = mapped is primary
                            mapped["source_hash"] = normalized_hash(mapped)
                            repository.upsert_sleep(mapped)
                    for row in reader.training_rows():
                        repository.upsert_training(map_training(row, reader))
                    for row in reader.weight_rows():
                        repository.upsert_body(
                            map_body(row, kind="weight", height_cm=height)
                        )
                    for row in reader.body_fat_rows():
                        repository.upsert_body(map_body(row, kind="body_fat"))
                    for record_date, values in reader.daily_summaries().items():
                        payload = dict(values)
                        payload["source_hash"] = normalized_hash(
                            {"record_date": record_date, **payload}
                        )
                        repository.upsert_daily(record_date, payload)
                    db.session.commit()
                    stats = repository.stats.as_dict()
                    run = db.session.get(HealthImportRun, run_id)
                    run.status = "completed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.imported_count = stats["imported"]
                    run.updated_count = stats["updated"]
                    run.skipped_count = stats["skipped"]
                    db.session.commit()
                    try:
                        create_notification(
                            notification_key=f"health-import:{run_id}:completed",
                            type="health_import_completed",
                            title="Dados de saúde importados",
                            message=(
                                f"{stats['imported']} registros novos e "
                                f"{stats['updated']} atualizados."
                            ),
                            action_url="/configuracoes",
                            severity="success",
                            source_type="health_import",
                            source_id=run_id,
                        )
                        incomplete_sleep = db.session.scalar(
                            db.select(SleepRecord.id).where(
                                SleepRecord.record_origin == "health_connect",
                                SleepRecord.suggestion_status == "available",
                            ).limit(1)
                        )
                        if incomplete_sleep:
                            create_notification(
                                notification_key=(
                                    f"health-import:{run_id}:incomplete-watch"
                                ),
                                type="incomplete_watch_record",
                                title="Complete seu sono",
                                message=(
                                    "Os dados do relógio foram importados. "
                                    "Falta informar como você acordou."
                                ),
                                action_url="/registrar?categoria=sleep",
                                severity="info",
                                source_type="health_import",
                                source_id=run_id,
                            )
                    except Exception:
                        db.session.rollback()
                        self.app.logger.exception(
                            "Falha ao criar notificação da importação."
                        )
                    return {"run_id": run_id, "status": run.status, **stats}
        except Exception as exc:
            with self.app.app_context():
                db.session.rollback()
                run = db.session.get(HealthImportRun, run_id)
                if run:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.error_count = 1
                    run.error_summary = str(exc)[:2000]
                    db.session.commit()
                    try:
                        create_notification(
                            notification_key=f"health-import:{run_id}:failed",
                            type="health_import_failed",
                            title="Falha na importação de saúde",
                            message=(
                                "A importação não foi concluída. "
                                "Revise a configuração e tente novamente."
                            ),
                            action_url="/configuracoes",
                            severity="error",
                            source_type="health_import",
                            source_id=run_id,
                        )
                    except Exception:
                        db.session.rollback()
                        self.app.logger.exception(
                            "Falha ao criar notificação de erro da importação."
                        )
            raise
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
