from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask_migrate import upgrade

from app import create_app


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: upgrade_database_file.py <condution_time.db>")
    database = Path(sys.argv[1]).resolve(strict=True)
    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (
        f"{database.stem}-before-schema-{datetime.now():%Y%m%d-%H%M%S}"
        f"{database.suffix}"
    )
    shutil.copy2(database, backup)

    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
            "TESTING": True,
        }
    )
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parents[1] / "migrations"))

    with sqlite3.connect(database) as connection:
        training_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(training_records)")
        }
        sleep_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sleep_records)")
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    required_training = {"manual_training_type", "vo2_max"}
    required_sleep = {"maximum_heart_rate", "is_primary"}
    valid = (
        required_training <= training_columns
        and required_sleep <= sleep_columns
        and "app_notifications" in tables
        and revision == "e6b9c3d7f204"
        and integrity == "ok"
    )
    print(
        json.dumps(
            {
                "database": str(database),
                "backup": str(backup),
                "revision": revision,
                "integrity": integrity,
                "verified": valid,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
