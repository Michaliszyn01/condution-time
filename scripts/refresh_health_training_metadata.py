from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.health_import.archive import prepare_database
from app.health_import.health_connect_reader import (
    HealthConnectReader,
    open_health_database,
)
from app.health_import.deduplication import normalized_hash
from app.health_import.mapper import map_sleep, map_training
from app.health_import.repository import HealthImportRepository
from app.models import SleepRecord, TrainingRecord


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Uso: refresh_health_training_metadata.py <condution_time.db> <export.zip>"
        )
    database = Path(sys.argv[1]).resolve(strict=True)
    archive = Path(sys.argv[2]).resolve(strict=True)
    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (
        f"{database.stem}-before-native-training-map-"
        f"{datetime.now():%Y%m%d-%H%M%S}{database.suffix}"
    )
    shutil.copy2(database, backup)
    work_dir = Path(".desktop-smoke/health-metadata-refresh").resolve()
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
            "TESTING": True,
        }
    )
    try:
        source_database = prepare_database(archive, work_dir)
        repository = HealthImportRepository()
        with open_health_database(source_database) as (connection, schema):
            reader = HealthConnectReader(
                connection,
                schema,
                timezone_name=app.config["APP_TIMEZONE"],
            )
            with app.app_context():
                before_count = int(
                    db.session.scalar(
                        db.select(db.func.count(TrainingRecord.id))
                    )
                    or 0
                )
                sleep_before_count = int(
                    db.session.scalar(db.select(db.func.count(SleepRecord.id))) or 0
                )
                before = {
                    record.source_record_id: {
                        "type": record.training_type,
                        "activity": record.activity_name,
                        "manual": record.manual_training_type,
                        "origin": record.record_origin,
                        "code": record.source_exercise_type,
                    }
                    for record in db.session.scalars(
                        db.select(TrainingRecord).where(
                            TrainingRecord.source_record_id.is_not(None)
                        )
                    )
                }
                for row in reader.training_rows():
                    repository.upsert_training(map_training(row, reader))
                sleeps_by_date = {}
                for row in reader.sleep_rows():
                    mapped = map_sleep(row, reader)
                    sleeps_by_date.setdefault(mapped["record_date"], []).append(mapped)
                for sessions in sleeps_by_date.values():
                    primary = max(
                        sessions,
                        key=lambda item: item["duration_minutes"],
                    )
                    for mapped in sessions:
                        mapped["is_primary"] = mapped is primary
                        mapped["source_hash"] = normalized_hash(mapped)
                        repository.upsert_sleep(mapped)
                db.session.commit()
                after_count = int(
                    db.session.scalar(
                        db.select(db.func.count(TrainingRecord.id))
                    )
                    or 0
                )
                sleep_after_count = int(
                    db.session.scalar(db.select(db.func.count(SleepRecord.id))) or 0
                )
                duplicate_sources = len(
                    list(
                        db.session.execute(
                        db.select(
                            TrainingRecord.source_record_id,
                            db.func.count(TrainingRecord.id),
                        )
                        .where(TrainingRecord.source_record_id.is_not(None))
                        .group_by(TrainingRecord.source_record_id)
                        .having(db.func.count(TrainingRecord.id) > 1)
                        )
                    )
                )
                types = Counter(
                    db.session.scalars(
                        db.select(TrainingRecord.training_type)
                    )
                )
                corrected_by_code = Counter()
                manual_preserved = 0
                for record in db.session.scalars(
                    db.select(TrainingRecord).where(
                        TrainingRecord.source_record_id.is_not(None)
                    )
                ):
                    old = before.get(record.source_record_id)
                    if not old:
                        continue
                    if old["type"] != record.training_type:
                        corrected_by_code[str(record.source_exercise_type)] += 1
                    if old["manual"] is not None:
                        assert old["manual"] == record.manual_training_type
                        manual_preserved += 1
        print(
            json.dumps(
                {
                    "before_count": before_count,
                    "after_count": after_count,
                    "sleep_before_count": sleep_before_count,
                    "sleep_after_count": sleep_after_count,
                    "duplicates": duplicate_sources,
                    "backup": str(backup),
                    "corrected_by_code": dict(sorted(corrected_by_code.items())),
                    "manual_preserved": manual_preserved,
                    "types": dict(sorted(types.items())),
                    **repository.stats.as_dict(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if before_count == after_count and duplicate_sources == 0 else 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
